#![allow(dead_code)]

pub mod admin;
pub mod checkout;
pub mod login;
pub mod pos;
pub mod widgets;

use crate::app::{App, Screen};
use crate::theme::{BORDER, CANVAS, INK, MUTED, WHITE};
use egui::{Align2, Context, FontId, Frame, Margin, CornerRadius, Stroke};

impl eframe::App for App {
    fn update(&mut self, ctx: &Context, _frame: &mut eframe::Frame) {
        self.draw(ctx);
    }
}

impl App {
    pub fn draw(&mut self, ctx: &Context) {
        // Data is refreshed only when a screen marks itself dirty.
        if self.screen == Screen::Pos {
            self.refresh_pos(ctx);
        } else if self.screen == Screen::Admin {
            self.refresh_admin(ctx);
        }

        match self.screen {
            Screen::Login => {
                egui::CentralPanel::default()
                    .frame(Frame::new().fill(WHITE))
                    .show(ctx, |ui| login::ui(self, ctx, ui));
            }
            Screen::Pos => {
                pos::top_bar(self, ctx);
                pos::ui(self, ctx);
                checkout::modal(self, ctx);
            }
            Screen::Admin => {
                if !self.is_owner() {
                    self.screen = Screen::Pos;
                    ctx.request_repaint();
                    return;
                }
                admin::shell(self, ctx);
            }
        }
        self.draw_status(ctx);
    }

    fn draw_status(&mut self, ctx: &Context) {
        let Some(status) = self.status.clone() else { return };
        egui::Window::new("status")
            .anchor(Align2::LEFT_BOTTOM, [0.0, 0.0])
            .title_bar(false)
            .resizable(false)
            .collapsible(false)
            .frame(
                Frame::new()
                    .fill(WHITE)
                    .stroke(Stroke::new(1.0_f32, BORDER))
                    .corner_radius(CornerRadius::same(crate::theme::RADIUS_SM))
                    .inner_margin(Margin::symmetric(14, 9)),
            )
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new(if status.error { "!" } else { "•" })
                            .font(FontId::new(13.0, egui::FontFamily::Proportional))
                            .color(INK)
                            .strong(),
                    );
                    ui.label(
                        egui::RichText::new(&status.text)
                            .color(INK)
                            .size(12.5),
                    );
                    if ui.add(
                        egui::Button::new(egui::RichText::new("×").size(13.0).color(MUTED))
                            .fill(egui::Color32::TRANSPARENT)
                            .stroke(egui::Stroke::NONE),
                    ).clicked() {
                        self.clear_status();
                    }
                });
            });
    }
}

/// Fill a panel area with the soft-white canvas colour.
pub fn canvas_frame() -> Frame {
    Frame::new().fill(CANVAS)
}

pub fn muted_color() -> egui::Color32 {
    MUTED
}
