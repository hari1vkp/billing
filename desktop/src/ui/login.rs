//! Login screen — black brand panel + centered white form.

use crate::app::App;
use crate::theme::*;
use crate::ui::widgets as w;
use egui::{Context, Frame, Layout, Margin, Response, CornerRadius, Stroke, Ui, Vec2};

const EMAIL_ID: &str = "login_email";

pub fn ui(app: &mut App, ctx: &Context, ui: &mut Ui) {
    ui.horizontal(|ui| {
        let total = ui.available_width();
        let brand_w = (total * 0.52).max(480.0);
        ui.allocate_ui(Vec2::new(brand_w, ui.available_height()), |ui| {
            brand_panel(ui);
        });
        ui.allocate_ui(Vec2::new(ui.available_width(), ui.available_height()), |ui| {
            form(app, ctx, ui);
        });
    });
}

fn brand_panel(ui: &mut Ui) {
    Frame::new()
        .fill(INK)
        .inner_margin(Margin::symmetric(48, 38))
        .show(ui, |ui| {
            ui.vertical(|ui| {
                // Mark + wordmark
                ui.horizontal(|ui| {
                    mark(ui, 38.0);
                    ui.add_space(10.0);
                    ui.vertical(|ui| {
                        ui.label(
                            egui::RichText::new("BillFlow")
                                .size(19.0)
                                .color(ON_DARK)
                                .strong(),
                        );
                        ui.label(
                            egui::RichText::new("Billing made simple")
                                .size(10.5)
                                .color(ON_DARK_MUTED),
                        );
                    });
                });

                ui.add_space(64.0);

                ui.label(
                    egui::RichText::new("  QUICK, CLEAN BILLING  ")
                        .size(11.0)
                        .color(ORANGE)
                        .strong()
                        .background_color(egui::Color32::from_rgba_unmultiplied(
                            0xFF, 0x6A, 0x00, 32,
                        )),
                );
                ui.add_space(18.0);
                ui.label(
                    egui::RichText::new("Every sale, in one place.")
                        .size(30.0)
                        .color(ON_DARK)
                        .strong(),
                );
                ui.add_space(12.0);
                ui.label(
                    egui::RichText::new(
                        "Scan a barcode, take the payment and close the bill — without the clutter. Built for the counter, with the reports you need at the end of the day.",
                    )
                    .size(14.0)
                    .color(ON_DARK_MUTED),
                );

                ui.add_space(34.0);
                feature(ui, "Scan & bill", "Keyboard-wedge barcode scanning with live cart totals.");
                ui.add_space(18.0);
                feature(ui, "Get paid your way", "UPI QR or cash, confirmed by the cashier in one tap.");
                ui.add_space(18.0);
                feature(ui, "Know your numbers", "Stock, customers and collections in a single console.");

                ui.add_space(34.0);
                Frame::new()
                    .fill(egui::Color32::from_rgba_premultiplied(0xF7, 0xF5, 0xF0, 18))
                    .stroke(Stroke::new(1.0_f32, egui::Color32::from_rgba_premultiplied(
                        0xF7, 0xF5, 0xF0, 52,
                    )))
                    .corner_radius(CornerRadius::same(10))
                    .inner_margin(Margin::symmetric(16, 14))
                    .show(ui, |ui| {
                        ui.label(
                            egui::RichText::new("Demo account")
                                .size(12.5)
                                .color(ON_DARK)
                                .strong(),
                        );
                        ui.add_space(8.0);
                        ui.horizontal(|ui| {
                            ui.label(
                                egui::RichText::new("demo@billingapp.com  /  Demo@1234")
                                    .font(egui::FontId::new(
                                        12.0,
                                        egui::FontFamily::Monospace,
                                    ))
                                    .color(ON_DARK),
                            );
                        });
                    });

                ui.add_space(20.0);
                ui.with_layout(Layout::bottom_up(egui::Align::LEFT), |ui| {
                    ui.label(
                        egui::RichText::new("BillFlow v1.0  ·  Local, private and fast")
                            .size(11.0)
                            .color(ON_DARK_MUTED),
                    );
                });
            });
        });
}

fn feature(ui: &mut Ui, title: &str, detail: &str) {
    ui.horizontal(|ui| {
        Frame::new()
            .fill(egui::Color32::from_rgba_premultiplied(0xF7, 0xF5, 0xF0, 26))
            .corner_radius(CornerRadius::same(10))
            .inner_margin(Margin::same(9))
            .show(ui, |ui| {
                ui.label(egui::RichText::new("+").size(16.0).color(ORANGE).strong());
            });
        ui.add_space(8.0);
        ui.vertical(|ui| {
            ui.label(egui::RichText::new(title).size(13.5).color(ON_DARK).strong());
            ui.label(egui::RichText::new(detail).size(11.5).color(ON_DARK_MUTED));
        });
    });
}

fn mark(ui: &mut Ui, size: f32) -> Response {
    Frame::new()
        .fill(ORANGE)
        .corner_radius(CornerRadius::same(10))
        .inner_margin(Margin::same(((size - 20.0) / 2.0) as i8))
        .show(ui, |ui| {
            ui.label(
                egui::RichText::new("▤")
                    .size(19.0)
                    .color(WHITE)
                    .strong(),
            );
        })
        .response
}

fn form(app: &mut App, ctx: &Context, ui: &mut Ui) {
    Frame::new()
        .fill(WHITE)
        .show(ui, |ui| {
            ui.vertical_centered(|ui| {
                ui.add_space((ui.available_height() - 430.0).max(30.0));
            });

            ui.vertical(|ui| {
                ui.horizontal(|ui| {
                    ui.add_space(56.0);
                    ui.vertical(|ui| {
                        ui.label(
                            egui::RichText::new("Welcome back")
                                .size(22.0)
                                .color(INK)
                                .strong(),
                        );
                        ui.add_space(4.0);
                        w::muted(ui, "Sign in to your BillFlow account");

                        ui.add_space(26.0);

                        w::field_label(ui, "Email address");
                        let email_id = egui::Id::new(EMAIL_ID);
                        if ui.memory(|m| m.focused().is_none()) {
                            ui.memory_mut(|m| m.request_focus(email_id));
                        }
                        let mut email_response = ui.add(
                            egui::TextEdit::singleline(&mut app.login.email)
                                .id(email_id)
                                .hint_text("you@business.com")
                                .desired_width(ui.available_width() - 8.0),
                        );
                        email_response.mark_changed();

                        ui.add_space(14.0);

                        w::field_label(ui, "Password");
                        ui.horizontal(|ui| {
                            let toggle_w = 58.0;
                            let field_w = ui.available_width() - toggle_w - 8.0;
                            let password = &mut app.login.password;
                            ui.add_sized(
                                [field_w, 38.0],
                                egui::TextEdit::singleline(password)
                                    .password(!app.login.show_password)
                                    .hint_text("Enter your password"),
                            );
                            let label = if app.login.show_password { "Hide" } else { "Show" };
                            if ui.add_sized([toggle_w, 34.0], egui::Button::new(
                                egui::RichText::new(label).size(12.0).color(ORANGE),
                            ).fill(egui::Color32::TRANSPARENT).stroke(Stroke::NONE)).clicked()
                            {
                                app.login.show_password = !app.login.show_password;
                            }
                        });

                        ui.add_space(10.0);
                        if w::link(ui, "Use demo credentials").clicked() {
                            app.fill_demo();
                        }

                        ui.add_space(18.0);
                        let sign_in = w::primary(ui, "Sign in");
                        if sign_in.clicked() || ctx.input_mut(|i| {
                            i.consume_key(egui::Modifiers::NONE, egui::Key::Enter)
                        }) {
                            app.login();
                        }

                        ui.add_space(26.0);
                        ui.label(
                            egui::RichText::new("Local account  ·  Your data stays on this device")
                                .size(11.0)
                                .color(MUTED),
                        );
                    });
                    ui.add_space(56.0);
                });
            });
        });
}
