//! Sales exports and PDF invoices.

use printpdf::{BuiltinFont, Mm, PdfDocument};
use rusqlite::Connection;

use crate::error::{BillflowError, Result};
use crate::models::{Business, Customer, Invoice, InvoiceItem};
use crate::repo;

fn csv_cell(value: &str) -> String {
    if value.contains([',', '"', '\n', '\r']) {
        format!("\"{}\"", value.replace('"', "\"\""))
    } else {
        value.to_string()
    }
}

/// A CSV export of all invoices in the (optional) date range.
pub fn sales_csv(
    conn: &Connection,
    business_id: &str,
    from: Option<&str>,
    to: Option<&str>,
) -> Result<String> {
    let mut sql = String::from(
        "SELECT i.invoice_number, i.issue_date, COALESCE(c.name, i.customer_name, ''), \
         i.status, i.subtotal, i.discount_amount, i.tax_amount, i.total_amount, \
         i.paid_amount, i.balance_amount \
         FROM invoices i LEFT JOIN customers c ON c.id = i.customer_id \
         WHERE i.business_id = ?1",
    );
    let mut values = vec![business_id.to_string()];
    if let Some(f) = from {
        values.push(f.to_string());
        sql.push_str(&format!(" AND i.issue_date >= ?{}", values.len()));
    }
    if let Some(t) = to {
        values.push(t.to_string());
        sql.push_str(&format!(" AND i.issue_date <= ?{}", values.len()));
    }
    sql.push_str(" ORDER BY i.issue_date DESC, i.created_at DESC");

    let mut stmt = conn.prepare(&sql)?;
    let mut rows = stmt.query(rusqlite::params_from_iter(values.iter()))?;
    let mut out = String::from(
        "Invoice Number,Date,Customer,Status,Subtotal,Discount,Tax,Total,Paid,Balance\n",
    );
    while let Some(row) = rows.next()? {
        let number: String = row.get(0)?;
        let date: String = row.get(1)?;
        let customer: String = row.get(2)?;
        let status: String = row.get(3)?;
        let amounts: [f64; 6] = [
            row.get(4)?,
            row.get(5)?,
            row.get(6)?,
            row.get(7)?,
            row.get(8)?,
            row.get(9)?,
        ];
        let mut cells = vec![
            csv_cell(&number),
            csv_cell(&date),
            csv_cell(&customer),
            csv_cell(&status),
        ];
        cells.extend(amounts.iter().map(|v| format!("{:.2}", v)));
        out.push_str(&cells.join(","));
        out.push('\n');
    }
    Ok(out)
}

fn safe_text(text: &str) -> String {
    text.chars().filter(|c| !matches!(c, '(' | ')' | '\\')).collect()
}

/// Render a one-page invoice as PDF bytes using `printpdf`.
pub fn invoice_pdf(
    business: &Business,
    customer: &Customer,
    invoice: &Invoice,
    items: &[InvoiceItem],
) -> Result<Vec<u8>> {
    let (doc, page, layer) = PdfDocument::new(
        format!("Invoice {}", invoice.invoice_number),
        Mm(210.0),
        Mm(297.0),
        "Invoice",
    );
    let current = doc.get_page(page).get_layer(layer);
    let regular = doc
        .add_builtin_font(BuiltinFont::Helvetica)
        .map_err(|e| BillflowError::Pdf(e.to_string()))?;
    let bold = doc
        .add_builtin_font(BuiltinFont::HelveticaBold)
        .map_err(|e| BillflowError::Pdf(e.to_string()))?;

    let mut y = 280.0f32;
    let step = |y: &mut f32, amount: f32| {
        *y -= amount;
    };

    current.use_text(safe_text(&business.name), 20.0, Mm(18.0), Mm(y), &bold);
    step(&mut y, 10.0);
    current.use_text("INVOICE", 12.0, Mm(18.0), Mm(y), &bold);
    step(&mut y, 7.0);
    current.use_text(
        safe_text(&format!("Number: {}", invoice.invoice_number)),
        10.0,
        Mm(18.0),
        Mm(y),
        &regular,
    );
    step(&mut y, 5.0);
    current.use_text(
        safe_text(&format!("Issue date: {}   Status: {}", invoice.issue_date, invoice.status.label())),
        10.0,
        Mm(18.0),
        Mm(y),
        &regular,
    );
    step(&mut y, 10.0);

    let address = [
        business.address.as_str(),
        business.city.as_str(),
        business.state.as_str(),
        business.pincode.as_str(),
    ]
    .iter()
    .filter(|part| !part.is_empty())
    .copied()
    .collect::<Vec<_>>()
    .join(", ");
    for line in [address, format!("GSTIN: {}", business.gstin), format!("Phone: {}", business.phone)] {
        if line.is_empty() || (line.contains(':') && line.ends_with(": ")) {
            continue;
        }
        current.use_text(safe_text(&line), 9.0, Mm(18.0), Mm(y), &regular);
        step(&mut y, 5.0);
    }

    step(&mut y, 6.0);
    current.use_text("BILL TO", 10.0, Mm(18.0), Mm(y), &bold);
    step(&mut y, 6.0);
    for line in [
        customer.name.clone(),
        customer.address.clone(),
        format!("{} {}, {} {}", customer.city, customer.state, customer.pincode, customer.gstin).trim().to_string(),
    ] {
        if line.trim().is_empty() {
            continue;
        }
        current.use_text(safe_text(&line), 9.0, Mm(18.0), Mm(y), &regular);
        step(&mut y, 5.0);
    }

    step(&mut y, 8.0);
    current.use_text("DESCRIPTION", 9.0, Mm(18.0), Mm(y), &bold);
    current.use_text("QTY", 9.0, Mm(110.0), Mm(y), &bold);
    current.use_text("RATE", 9.0, Mm(130.0), Mm(y), &bold);
    current.use_text("GST", 9.0, Mm(150.0), Mm(y), &bold);
    current.use_text("AMOUNT", 9.0, Mm(168.0), Mm(y), &bold);
    step(&mut y, 6.0);

    for item in items {
        current.use_text(safe_text(&item.description), 9.0, Mm(18.0), Mm(y), &regular);
        current.use_text(format!("{}", item.quantity), 9.0, Mm(110.0), Mm(y), &regular);
        current.use_text(format!("{:.2}", item.unit_price), 9.0, Mm(130.0), Mm(y), &regular);
        current.use_text(format!("{}%", item.gst_rate), 9.0, Mm(150.0), Mm(y), &regular);
        current.use_text(format!("{:.2}", item.line_total), 9.0, Mm(168.0), Mm(y), &regular);
        step(&mut y, 6.0);
        if y < 45.0 {
            break;
        }
    }

    step(&mut y, 8.0);
    for (label, value) in [
        ("Subtotal", invoice.subtotal),
        ("Item discounts", -invoice.discount_amount),
        ("Taxable amount", invoice.taxable_amount),
        ("GST", invoice.tax_amount),
    ] {
        current.use_text(label, 9.0, Mm(120.0), Mm(y), &regular);
        current.use_text(format!("{} {:.2}", business.currency, value), 9.0, Mm(168.0), Mm(y), &regular);
        step(&mut y, 5.0);
    }
    step(&mut y, 3.0);
    current.use_text("TOTAL PAYABLE", 11.0, Mm(120.0), Mm(y), &bold);
    current.use_text(
        format!("{} {:.2}", business.currency, invoice.total_amount),
        11.0,
        Mm(168.0),
        Mm(y),
        &bold,
    );
    step(&mut y, 6.0);
    current.use_text(
        format!("Paid: {:.2}   Balance: {:.2}", invoice.paid_amount, invoice.balance_amount),
        9.0,
        Mm(120.0),
        Mm(y),
        &regular,
    );

    if let Some(footer) = &business.invoice_footer {
        current.use_text(safe_text(footer), 8.0, Mm(18.0), Mm(18.0), &regular);
    }

    doc.save_to_bytes().map_err(|e| BillflowError::Pdf(e.to_string()))
}

/// Convenience wrapper for callers that only have a database connection.
pub fn invoice_pdf_for(
    conn: &Connection,
    business_id: &str,
    invoice_id: &str,
) -> Result<Vec<u8>> {
    let business = repo::get_business(conn, business_id)?;
    let detail = repo::get_invoice(conn, business_id, invoice_id)?;
    let customer = repo::get_customer(conn, business_id, &detail.invoice.customer_id)?
        .ok_or_else(|| BillflowError::NotFound("Customer not found".into()))?;
    invoice_pdf(&business, &customer, &detail.invoice, &detail.items)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn csv_cell_quotes_commas() {
        assert_eq!(csv_cell("plain"), "plain");
        assert_eq!(csv_cell("a,b"), "\"a,b\"");
        assert_eq!(csv_cell("a\"b"), "\"a\"\"b\"");
    }
}
