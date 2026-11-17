//! Login screen — full-height black brand panel + vertically centred white form.
//! Mirrors the web `.auth-page` grid: `1.05fr 1fr`.

use crate::app::App;
use crate::theme::*;
use crate::ui::widgets as w;
use egui::{
    Align, Context, CornerRadius, Frame, Layout, Margin, Response, RichText, Stroke, Ui,
};

const EMAIL_ID: &str = "login_email";
const BRAND_PAD_X: f32 = 56.0;

pub fn ui(app: &mut App, ctx: &Context) {
    // A SidePanel spans the entire window height, which is what the web brand
    // panel does. The CentralPanel fills the remaining area on the right.
    let brand_w = ctx.screen_rect().width() * (1.05 / 2.05);
    egui::SidePanel::left("login_brand")
        .exact_width(brand_w)
        .resizable(false)
        .frame(Frame::new().fill(INK))
        .show(ctx, |ui| {
            egui::ScrollArea::vertical()
                .id_salt("login_brand_scroll")
                .auto_shrink([false, false])
                .show(ui, |ui| brand_panel(ui));
        });

    egui::CentralPanel::default()
        .frame(Frame::new().fill(WHITE))
        .show(ctx, |ui| {
            // The form is centred in the remaining area and scrolls if the
            // window is short, so the eye-toggle and demo hint are never cut.
            egui::ScrollArea::vertical()
                .id_salt("login_form_scroll")
                .show(ui, |ui| {
                    ui.centered_and_justified(|ui| {
                        ui.set_max_width(400.0);
                        form(app, ctx, ui);
                    });
                });
        });
}

fn brand_panel(ui: &mut Ui) {
    ui.vertical(|ui| {
        // ---- top: logo, headline, body, features -------------------------
        ui.add_space(42.0);
        ui.horizontal(|ui| {
            ui.add_space(BRAND_PAD_X);
            ui.vertical(|ui| {
                ui.horizontal(|ui| {
                    mark(ui, 36.0);
                    ui.add_space(10.0);
                    ui.vertical(|ui| {
                        ui.label(RichText::new("BillFlow").size(20.0).color(ON_DARK));
                        ui.label(
                            RichText::new("Billing made simple")
                                .size(10.5)
                                .color(ON_DARK_MUTED),
                        );
                    });
                });

                ui.add_space(60.0);

                ui.label(
                    RichText::new("  ✦  All-in-one business billing  ")
                        .size(11.0)
                        .color(ORANGE)
                        .strong()
                        .background_color(egui::Color32::from_rgba_unmultiplied(
                            0xFF, 0x6A, 0x00, 38,
                        )),
                );
                ui.add_space(20.0);
                ui.label(
                    RichText::new("Invoice smarter.\nGet paid faster.")
                        .size(30.0)
                        .color(ON_DARK),
                );
                ui.add_space(18.0);
                ui.label(
                    RichText::new(
                        "Billing, customer relationships and real-time analytics — thoughtfully brought together in one clean workspace.",
                    )
                    .size(14.5)
                    .color(ON_DARK_MUTED),
                );

                ui.add_space(40.0);
                feature(
                    ui,
                    "GST-ready invoicing",
                    "Professional invoices with tax and a UPI QR in seconds.",
                );
                ui.add_space(20.0);
                feature(
                    ui,
                    "Payments without the chase",
                    "Share payment links, collect declarations and reconcile instantly.",
                );
                ui.add_space(20.0);
                feature(
                    ui,
                    "Clarity at a glance",
                    "Track sales, collections and outstanding balances as they happen.",
                );
            });
        });

        // ---- bottom: demo card + footer pinned to the bottom -------------
        ui.with_layout(Layout::bottom_up(Align::LEFT), |ui| {
            ui.add_space(28.0);
            ui.horizontal(|ui| {
                ui.add_space(BRAND_PAD_X);
                ui.label(
                    RichText::new("© 2026 BillFlow. Built for growing businesses.")
                        .size(11.0)
                        .color(ON_DARK_MUTED),
                );
            });
            ui.add_space(20.0);
            ui.horizontal(|ui| {
                ui.add_space(BRAND_PAD_X);
                demo_card(app, ui);
            });
        });
    });
}

fn demo_card(app: &mut App, ui: &mut Ui) {
    Frame::new()
        .fill(egui::Color32::from_rgba_premultiplied(0xF7, 0xF5, 0xF0, 16))
        .stroke(Stroke::new(
            1.0_f32,
            egui::Color32::from_rgba_premultiplied(0xF7, 0xF5, 0xF0, 50),
        ))
        .corner_radius(CornerRadius::same(10))
        .inner_margin(Margin::symmetric(17, 15))
        .show(ui, |ui| {
            ui.label(
                RichText::new("Explore with the demo account")
                    .size(12.5)
                    .color(ON_DARK)
                    .strong(),
            );
            ui.add_space(10.0);
            ui.horizontal(|ui| {
                ui.label(
                    RichText::new("demo@billingapp.com")
                        .font(egui::FontId::new(12.0, egui::FontFamily::Monospace))
                        .color(ON_DARK),
                );
                ui.label(RichText::new("·").color(ON_DARK_MUTED));
                ui.label(
                    RichText::new("Demo@1234")
                        .font(egui::FontId::new(12.0, egui::FontFamily::Monospace))
                        .color(ON_DARK),
                );
            });
            ui.add_space(12.0);
            if w::link(ui, "Use demo credentials  →").clicked() {
                app.fill_demo();
            }
        });
}

fn feature(ui: &mut Ui, title: &str, detail: &str) {
    ui.horizontal(|ui| {
        Frame::new()
            .fill(egui::Color32::from_rgba_premultiplied(0xF7, 0xF5, 0xF0, 26))
            .corner_radius(CornerRadius::same(10))
            .inner_margin(Margin::same(9))
            .show(ui, |ui| {
                ui.label(RichText::new("+").size(17.0).color(ORANGE).strong());
            });
        ui.add_space(13.0);
        ui.vertical(|ui| {
            ui.label(RichText::new(title).size(13.5).color(ON_DARK).strong());
            ui.label(RichText::new(detail).size(12.0).color(ON_DARK_MUTED));
        });
    });
}

fn mark(ui: &mut Ui, size: f32) -> Response {
    Frame::new()
        .fill(ORANGE)
        .corner_radius(CornerRadius::same(10))
        .inner_margin(Margin::symmetric(((size - 20.0) / 2.0) as i8, ((size - 20.0) / 2.0) as i8))
        .show(ui, |ui| {
            ui.label(RichText::new("▤").size(19.0).color(WHITE).strong());
        })
        .response
}

fn form(app: &mut App, ctx: &Context, ui: &mut Ui) {
    ui.vertical(|ui| {
        ui.label(RichText::new("Welcome back").size(22.0).color(INK).strong());
        ui.add_space(6.0);
        w::muted(ui, "Sign in to your BillFlow account");

        ui.add_space(26.0);

        w::field_label(ui, "Email address");
        let email_id = egui::Id::new(EMAIL_ID);
        if ui.memory(|m| m.focused().is_none()) {
            ui.memory_mut(|m| m.request_focus(email_id));
        }
        let field_w = ui.available_width();
        let mut email_response = ui.add_sized(
            [field_w, 46.0],
            egui::TextEdit::singleline(&mut app.login.email)
                .id(email_id)
                .hint_text("you@business.com")
                .desired_width(field_w),
        );
        email_response.mark_changed();

        ui.add_space(16.0);

        w::field_label(ui, "Password");
        ui.horizontal(|ui| {
            let toggle_w = 56.0;
            let field_w = ui.available_width() - toggle_w;
            ui.add_sized(
                [field_w, 46.0],
                egui::TextEdit::singleline(&mut app.login.password)
                    .password(!app.login.show_password)
                    .hint_text("Enter your password")
                    .desired_width(field_w),
            );
            let label = if app.login.show_password { "Hide" } else { "Show" };
            if ui
                .add_sized(
                    [toggle_w, 46.0],
                    egui::Button::new(RichText::new(label).size(12.0).color(ORANGE))
                        .fill(egui::Color32::TRANSPARENT)
                        .stroke(Stroke::NONE),
                )
                .clicked()
            {
                app.login.show_password = !app.login.show_password;
            }
        });

        ui.add_space(10.0);
        if w::link(ui, "Use demo credentials").clicked() {
            app.fill_demo();
        }

        ui.add_space(20.0);
        let sign_in = w::primary(ui, "Sign in");
        if sign_in.clicked()
            || ctx.input_mut(|i| i.consume_key(egui::Modifiers::NONE, egui::Key::Enter))
        {
            app.login();
        }

        ui.add_space(26.0);
        ui.label(
            RichText::new("Local account  ·  Your data stays on this device")
                .size(11.5)
                .color(MUTED),
        );
    });
}
