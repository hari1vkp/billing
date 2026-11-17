//! Checkout modal — UPI QR / Cash only, then a compact paid receipt.

use egui::{Align2, Context, Frame, Layout, Margin, CornerRadius, Stroke, Vec2};

use crate::app::{App, Receipt};
use crate::theme::*;
use crate::ui::widgets as w;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum PaymentTab {
    Upi,
    Cash,
}

#[derive(Clone, Debug)]
pub struct CheckoutState {
    pub invoice_number: String,
    pub tab: PaymentTab,
    pub total: f64,
    pub qr_error: Option<String>,
    pub receipt: Option<Receipt>,
    pub completing: bool,
}

pub fn modal(app: &mut App, ctx: &Context) {
    if app.checkout.is_none() {
        return;
    }
    let receipt = app.checkout.as_ref().and_then(|c| c.receipt.clone());
    let title = if receipt.is_some() { "Sale completed" } else { "Checkout" };

    egui::Window::new(title)
        .collapsible(false)
        .resizable(false)
        .anchor(Align2::CENTER_CENTER, Vec2::ZERO)
        .frame(
            Frame::new()
                .fill(WHITE)
                .stroke(Stroke::new(1.0_f32, BORDER))
                .corner_radius(CornerRadius::same(10))
                .inner_margin(Margin::same(24)),
        )
        .show(ctx, |ui| {
            ui.set_width(430.0);
            if let Some(receipt) = receipt {
                receipt_view(app, ui, &receipt);
            } else {
                checkout_view(app, ui);
            }
        });
}

fn checkout_view(app: &mut App, ui: &mut egui::Ui) {
    let business_name = app
        .business
        .as_ref()
        .map(|b| b.name.clone())
        .unwrap_or_else(|| "BillFlow".to_string());
    let invoice = app
        .checkout
        .as_ref()
        .map(|c| c.invoice_number.clone())
        .unwrap_or_default();
    let total = app.checkout.as_ref().map(|c| c.total).unwrap_or(0.0);

    w::muted(ui, business_name);
    ui.add_space(8.0);
    ui.horizontal(|ui| {
        ui.vertical(|ui| {
            w::caption(ui, "Invoice");
            ui.label(
                egui::RichText::new(&invoice)
                    .size(16.0)
                    .color(INK)
                    .strong(),
            );
        });
        ui.with_layout(Layout::right_to_left(egui::Align::TOP), |ui| {
            ui.vertical(|ui| {
                ui.with_layout(Layout::right_to_left(egui::Align::TOP), |ui| {
                    w::caption(ui, "Total payable");
                });
                ui.label(w::money_text(total, 24.0, INK));
            });
        });
    });

    ui.add_space(18.0);
    ui.separator();
    ui.add_space(12.0);

    // Exactly two tabs: UPI QR and Cash.
    ui.horizontal(|ui| {
        let selected = app.checkout.as_ref().map(|c| c.tab).unwrap_or(PaymentTab::Upi);
        if tab_button(ui, "UPI QR", selected == PaymentTab::Upi).clicked() {
            if let Some(c) = app.checkout.as_mut() {
                c.tab = PaymentTab::Upi;
            }
        }
        if tab_button(ui, "Cash", selected == PaymentTab::Cash).clicked() {
            if let Some(c) = app.checkout.as_mut() {
                c.tab = PaymentTab::Cash;
            }
        }
    });
    ui.add_space(14.0);

    let tab = app.checkout.as_ref().map(|c| c.tab).unwrap_or(PaymentTab::Upi);
    match tab {
        PaymentTab::Upi => {
            if let Some(texture) = app.qr_texture.as_ref() {
                ui.vertical_centered(|ui| {
                    let sized = egui::load::SizedTexture::from_handle(texture);
                    let image = egui::Image::new(sized).fit_to_exact_size(Vec2::splat(216.0));
                    ui.add(image);
                });
                ui.add_space(8.0);
                let upi = app
                    .business
                    .as_ref()
                    .map(|b| b.upi_id.clone())
                    .unwrap_or_default();
                ui.vertical_centered(|ui| {
                    ui.label(
                        egui::RichText::new(&upi)
                            .font(egui::FontId::new(12.5, egui::FontFamily::Monospace))
                            .color(INK),
                    );
                    ui.add_space(5.0);
                    w::caption(ui, format!("Customer scans and pays {}", app.money(total)));
                });
            } else {
                let error = app
                    .checkout
                    .as_ref()
                    .and_then(|c| c.qr_error.clone())
                    .unwrap_or_else(|| "UPI QR is unavailable for this business.".to_string());
                ui.vertical_centered(|ui| {
                    ui.add_space(40.0);
                    w::muted(ui, error);
                    ui.add_space(40.0);
                });
            }
        }
        PaymentTab::Cash => {
            ui.vertical_centered(|ui| {
                ui.add_space(22.0);
                w::caption(ui, "Collect exactly");
                ui.add_space(6.0);
                ui.label(w::money_text(total, 28.0, INK));
                ui.add_space(14.0);
                w::caption(ui, "Confirm the cash in hand, then complete the sale.");
                ui.add_space(22.0);
            });
        }
    }

    ui.add_space(12.0);
    ui.separator();
    ui.add_space(12.0);
    ui.horizontal(|ui| {
        if w::secondary(ui, "Cancel").clicked() {
            // Cancel closes without touching the database; the cart is intact.
            app.close_checkout();
        }
        ui.with_layout(Layout::right_to_left(egui::Align::Center), |ui| {
            let completing = app.checkout.as_ref().map(|c| c.completing).unwrap_or(false);
            if w::primary(ui, if completing { "Completing…" } else { "Complete Sale" }).clicked() {
                app.complete_sale();
            }
        });
    });
}

fn tab_button(ui: &mut egui::Ui, text: &str, active: bool) -> egui::Response {
    let (fill, color, stroke) = if active {
        (ORANGE, WHITE, Stroke::NONE)
    } else {
        (WHITE, MUTED, Stroke::new(1.0_f32, BORDER))
    };
    ui.add_sized(
        [104.0, 32.0],
        egui::Button::new(egui::RichText::new(text).size(12.5).color(color).strong())
            .fill(fill)
            .stroke(stroke)
            .corner_radius(CornerRadius::same(7)),
    )
}

fn receipt_view(app: &mut App, ui: &mut egui::Ui, receipt: &Receipt) {
    ui.vertical_centered(|ui| {
        ui.add_space(8.0);
        Frame::new()
            .fill(INK)
            .corner_radius(CornerRadius::same(12))
            .inner_margin(Margin::same(14))
            .show(ui, |ui| {
                ui.label(egui::RichText::new("✓").size(24.0).color(WHITE).strong());
            });
        ui.add_space(12.0);
        w::caption(ui, "Amount received");
        ui.add_space(4.0);
        ui.label(w::money_text(receipt.amount, 30.0, INK));
        ui.add_space(18.0);
    });

    Frame::new()
        .fill(SUBTLE)
        .corner_radius(CornerRadius::same(RADIUS))
        .inner_margin(Margin::symmetric(14, 12))
        .show(ui, |ui| {
            receipt_row(ui, "Invoice", &receipt.invoice_number);
            receipt_row(
                ui,
                "Method",
                match receipt.method {
                    billflow_shared::models::PaymentMethod::Upi => "UPI QR",
                    billflow_shared::models::PaymentMethod::Cash => "Cash",
                },
            );
            receipt_row(ui, "Status", "Paid");
        });
    ui.add_space(10.0);
    w::caption(ui, &receipt.note);
    ui.add_space(16.0);
    if w::primary(ui, "New Sale").clicked() {
        app.new_sale();
    }
}

fn receipt_row(ui: &mut egui::Ui, label: &str, value: &str) {
    ui.horizontal(|ui| {
        w::muted(ui, label);
        ui.with_layout(Layout::right_to_left(egui::Align::Center), |ui| {
            ui.label(
                egui::RichText::new(value)
                    .size(12.5)
                    .color(INK)
                    .strong(),
            );
        });
    });
}
