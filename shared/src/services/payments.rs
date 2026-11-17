//! UPI helpers, QR generation and payment confirmation.

use image::{codecs::png::PngEncoder, ExtendedColorType, ImageBuffer, ImageEncoder, Luma};
use qrcode::{Color, QrCode};
use rusqlite::{params, Connection, OptionalExtension};

use crate::audit;
use crate::error::{BillflowError, Result};
use crate::money::round2;
use crate::models::{InvoiceStatus, Payment};
use crate::repo;
use crate::util;

/// Build an NPCI-compatible UPI deep link.
pub fn build_upi_uri(vpa: &str, payee: &str, amount: f64, reference: &str, currency: &str) -> String {
    let mut uri = String::from("upi://pay?");
    uri.push_str("pa=");
    uri.push_str(&percent_encode(vpa.trim()));
    uri.push_str("&pn=");
    uri.push_str(&percent_encode(payee.trim()));
    uri.push_str("&am=");
    uri.push_str(&format!("{:.2}", amount));
    uri.push_str("&cu=");
    uri.push_str(&percent_encode(if currency.is_empty() { "INR" } else { currency }));
    if !reference.is_empty() {
        uri.push_str("&tr=");
        uri.push_str(&percent_encode(reference));
    }
    uri
}

fn percent_encode(input: &str) -> String {
    let mut out = String::with_capacity(input.len());
    for &byte in input.as_bytes() {
        if byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b'~') {
            out.push(byte as char);
        } else {
            out.push('%');
            out.push_str(&format!("{:02X}", byte));
        }
    }
    out
}

/// QR modules as `(side_length, row-major booleans)`.
pub fn qr_matrix(uri: &str) -> Result<(usize, Vec<bool>)> {
    let qr = QrCode::new(uri).map_err(|e| BillflowError::Qr(e.to_string()))?;
    let side = qr.width();
    let mut modules = Vec::with_capacity(side * side);
    for y in 0..side {
        for x in 0..side {
            modules.push(qr[(x, y)] == Color::Dark);
        }
    }
    Ok((side, modules))
}

/// Render the URI as a quiet-zone padded PNG image.
pub fn qr_png(uri: &str) -> Result<Vec<u8>> {
    let (side, modules) = qr_matrix(uri)?;
    const BORDER: u32 = 4;
    const SCALE: u32 = 8;
    let dimension = (side as u32 + 2 * BORDER) * SCALE;
    let mut image: ImageBuffer<Luma<u8>, Vec<u8>> = ImageBuffer::new(dimension, dimension);
    for (x, y, pixel) in image.enumerate_pixels_mut() {
        let mx = x / SCALE;
        let my = y / SCALE;
        let dark = mx >= BORDER
            && my >= BORDER
            && mx < BORDER + side as u32
            && my < BORDER + side as u32
            && modules[((my - BORDER) as usize) * side + ((mx - BORDER) as usize)];
        *pixel = Luma([if dark { 0 } else { 255 }]);
    }

    let mut bytes = Vec::new();
    PngEncoder::new(&mut bytes)
        .write_image(image.as_raw(), dimension, dimension, ExtendedColorType::L8)
        .map_err(|e| BillflowError::Qr(e.to_string()))?;
    Ok(bytes)
}

/// Confirm a pending payment: update invoice totals, adjust stock once and log.
///
/// This is the single implementation shared by the standalone confirm endpoint
/// and the POS checkout, so the stock decrement can never be applied twice.
pub(crate) fn confirm_inner(
    conn: &Connection,
    business_id: &str,
    payment_id: &str,
    user_id: Option<&str>,
    reference: &str,
) -> Result<Payment> {
    let payment = repo::get_payment(conn, business_id, payment_id)?;
    if payment.status == "confirmed" {
        return Ok(payment);
    }
    if payment.status == "refunded" || payment.status == "failed" {
        return Err(BillflowError::Validation(format!(
            "Cannot confirm a {} payment",
            payment.status
        )));
    }

    let detail = repo::get_invoice(conn, business_id, &payment.invoice_id)?;
    let invoice = detail.invoice;
    if invoice.status == InvoiceStatus::Cancelled {
        return Err(BillflowError::Validation("Invoice is not available for payment".into()));
    }

    let now = util::now_iso();
    let reference = reference.trim();
    let new_ref = if reference.is_empty() {
        payment.reference.clone()
    } else {
        Some(reference.to_string())
    };
    conn.execute(
        "UPDATE payments SET status='confirmed', confirmed_at=?1, \
         confirmed_by=COALESCE(?2, confirmed_by), reference=COALESCE(?3, reference), \
         payment_date=COALESCE(payment_date, ?4), \
         notes=COALESCE(notes, 'Manually confirmed by cashier') WHERE id=?5",
        params![now, user_id, new_ref, util::today(), payment_id],
    )?;

    let paid = round2(invoice.paid_amount + payment.amount);
    let balance = round2((invoice.total_amount - paid).max(0.0));
    let new_status = if paid <= 0.0 {
        if invoice.status == InvoiceStatus::Draft {
            InvoiceStatus::Draft
        } else {
            InvoiceStatus::Unpaid
        }
    } else if paid >= invoice.total_amount {
        InvoiceStatus::Paid
    } else {
        InvoiceStatus::PartiallyPaid
    };
    conn.execute(
        "UPDATE invoices SET paid_amount=?1, balance_amount=?2, status=?3, updated_at=?4 \
         WHERE id=?5",
        params![paid, balance, new_status.as_str(), now, invoice.id],
    )?;

    // Decrement inventory exactly once per payment.
    let adjusted: bool = conn.query_row(
        "SELECT stock_adjusted FROM payments WHERE id = ?1",
        params![payment_id],
        |row| row.get::<_, i64>(0).map(|v| v != 0),
    )?;
    if !adjusted {
        let actor = audit::actor_name(conn, user_id);
        for item in &detail.items {
            let Some(product_id) = item.product_id.as_deref() else { continue };
            let product: Option<(String, f64, bool, Option<String>, Option<String>)> = conn
                .query_row(
                    "SELECT name, stock, track_inventory, sku, barcode FROM products WHERE id=?1",
                    params![product_id],
                    |row| {
                        Ok((
                            row.get(0)?,
                            row.get(1)?,
                            row.get::<_, i64>(2)? != 0,
                            row.get(3)?,
                            row.get(4)?,
                        ))
                    },
                )
                .optional()?;
            let Some((name, before, tracked, sku, barcode)) = product else { continue };
            if !tracked {
                continue;
            }
            let change = -item.quantity;
            let after = (before + change).max(0.0);
            conn.execute(
                "UPDATE products SET stock=?1, updated_at=?2 WHERE id=?3",
                params![after, now, product_id],
            )?;
            conn.execute(
                "INSERT INTO stock_movements (id, business_id, product_id, product_name, sku, \
                 barcode, quantity_change, quantity_before, quantity_after, reason, reference, \
                 performed_by_name, notes, created_at) \
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, 'sale', ?10, ?11, ?12, ?13)",
                params![
                    util::uuid(),
                    business_id,
                    product_id,
                    name,
                    sku,
                    barcode,
                    change,
                    before,
                    after,
                    invoice.invoice_number,
                    actor,
                    format!("Payment {}", payment_id),
                    now,
                ],
            )?;
        }
        conn.execute(
            "UPDATE payments SET stock_adjusted = 1 WHERE id = ?1",
            params![payment_id],
        )?;
    }

    let reference_for_log = new_ref.clone().unwrap_or_else(|| invoice.invoice_number.clone());
    audit::log(
        conn,
        business_id,
        user_id,
        "payment.confirm",
        "payment",
        Some(&reference_for_log),
        Some(&format!("amount={:.2} method={} invoice={}", payment.amount, payment.method.as_str(), invoice.invoice_number)),
    )?;

    repo::get_payment(conn, business_id, payment_id)
}

/// Confirm a payment in a single all-or-nothing transaction.
pub fn confirm_payment(
    conn: &Connection,
    business_id: &str,
    payment_id: &str,
    user_id: &str,
    reference: &str,
) -> Result<Payment> {
    let tx = conn.unchecked_transaction()?;
    let payment = confirm_inner(&tx, business_id, payment_id, Some(user_id), reference)?;
    tx.commit()?;
    Ok(payment)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn builds_upi_uri_with_expected_parameters() {
        let uri = build_upi_uri("demo@upi", "Demo Store", 1234.5, "POS-ABC", "INR");
        assert!(uri.starts_with("upi://pay?"));
        assert!(uri.contains("pa=demo%40upi"));
        assert!(uri.contains("pn=Demo%20Store"));
        assert!(uri.contains("am=1234.50"));
        assert!(uri.contains("cu=INR"));
        assert!(uri.contains("tr=POS-ABC"));
    }

    #[test]
    fn qr_png_is_a_png_and_matrix_is_nonempty() {
        let uri = "upi://pay?pa=demo%40upi&am=10.00";
        let (side, modules) = qr_matrix(uri).unwrap();
        assert!(side > 0);
        assert_eq!(modules.len(), side * side);
        let png = qr_png(uri).unwrap();
        assert_eq!(&png[..8], &[0x89, b'P', b'N', b'G', 0x0D, 0x0A, 0x1A, 0x0A]);
    }
}
