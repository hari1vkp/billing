//! Small, reusable egui building blocks that mirror the BillFlow web design
//! system: white cards, 1px borders, 8px radii and orange only on interactions.
#![allow(dead_code)]

use billflow_shared::money::format_inr;
use egui::{
    Align, Color32, FontFamily, FontId, Frame, Layout, Margin, Response, RichText, CornerRadius, Stroke,
    TextEdit, TextStyle, Ui, Vec2,
};

use crate::theme::*;

pub fn card_frame() -> Frame {
    Frame::new()
        .fill(WHITE)
        .stroke(Stroke::new(1.0_f32, BORDER))
        .corner_radius(RADIUS)
        .inner_margin(Margin::same(18))
}

pub fn card(ui: &mut Ui, add_contents: impl FnOnce(&mut Ui)) -> Response {
    card_frame().show(ui, add_contents).response
}

pub fn flat_card(ui: &mut Ui, add_contents: impl FnOnce(&mut Ui)) -> Response {
    Frame::new()
        .fill(WHITE)
        .stroke(Stroke::new(1.0_f32, BORDER))
        .corner_radius(RADIUS)
        .inner_margin(Margin::same(16))
        .show(ui, add_contents)
        .response
}

pub fn primary(ui: &mut Ui, text: impl Into<String>) -> Response {
    button(ui, text, ORANGE, WHITE, Stroke::NONE, true)
}

pub fn secondary(ui: &mut Ui, text: impl Into<String>) -> Response {
    button(ui, text, WHITE, INK, Stroke::new(1.0_f32, BORDER), true)
}

pub fn ghost(ui: &mut Ui, text: impl Into<String>) -> Response {
    button(ui, text, Color32::TRANSPARENT, MUTED, Stroke::NONE, true)
}

pub fn dark_button(ui: &mut Ui, text: impl Into<String>) -> Response {
    button(ui, text, INK, WHITE, Stroke::NONE, true)
}

pub fn small_button(ui: &mut Ui, text: impl Into<String>) -> Response {
    let text = RichText::new(text).size(11.5).color(INK);
    ui.add_sized(
        [64.0, 26.0],
        egui::Button::new(text)
            .fill(WHITE)
            .stroke(Stroke::new(1.0_f32, BORDER))
            .corner_radius(CornerRadius::same(RADIUS_SM)),
    )
}

pub fn link(ui: &mut Ui, text: impl Into<String>) -> Response {
    ui.add(
        egui::Button::new(RichText::new(text).size(12.5).color(ORANGE))
            .fill(Color32::TRANSPARENT)
            .stroke(Stroke::NONE)
            .corner_radius(CornerRadius::same(4)),
    )
}

pub fn button(
    ui: &mut Ui,
    text: impl Into<String>,
    fill: Color32,
    text_color: Color32,
    stroke: Stroke,
    enabled: bool,
) -> Response {
    let text = RichText::new(text).size(13.0).color(text_color).strong();
    ui.add_enabled(
        enabled,
        egui::Button::new(text)
            .fill(fill)
            .stroke(stroke)
            .corner_radius(CornerRadius::same(RADIUS))
            .min_size(Vec2::new(0.0, 34.0)),
    )
}

pub fn text_input(ui: &mut Ui, value: &mut String, hint: &str, width: f32) -> Response {
    ui.add_sized(
        [width, 38.0],
        TextEdit::singleline(value)
            .hint_text(RichText::new(hint).color(MUTED).size(12.5))
            .text_color(INK)
            .desired_width(width),
    )
}

pub fn password_input(ui: &mut Ui, value: &mut String, hint: &str, show: bool, width: f32) -> Response {
    ui.add_sized(
        [width, 38.0],
        TextEdit::singleline(value)
            .password(!show)
            .hint_text(RichText::new(hint).color(MUTED).size(12.5))
            .text_color(INK)
            .desired_width(width),
    )
}

pub fn small_input(ui: &mut Ui, value: &mut String, hint: &str, width: f32) -> Response {
    ui.add_sized(
        [width, 30.0],
        TextEdit::singleline(value)
            .hint_text(hint)
            .text_color(INK)
            .desired_width(width),
    )
}

pub fn number_input(ui: &mut Ui, value: &mut String, hint: &str, width: f32) -> Response {
    ui.add_sized(
        [width, 34.0],
        TextEdit::singleline(value)
            .hint_text(hint)
            .text_color(INK)
            .desired_width(width),
    )
}

pub fn label(ui: &mut Ui, text: impl Into<String>, color: Color32, size: f32) -> Response {
    ui.label(RichText::new(text).color(color).size(size))
}

pub fn muted(ui: &mut Ui, text: impl Into<String>) -> Response {
    label(ui, text, MUTED, 12.5)
}

pub fn caption(ui: &mut Ui, text: impl Into<String>) -> Response {
    label(ui, text, MUTED, 11.0)
}

pub fn section_title(ui: &mut Ui, title: &str, subtitle: Option<&str>) {
    ui.label(RichText::new(title).size(16.0).color(INK));
    if let Some(sub) = subtitle {
        ui.add_space(3.0);
        muted(ui, sub);
    }
}

pub fn page_header(ui: &mut Ui, title: &str, subtitle: &str) {
    ui.label(RichText::new(title).size(21.0).color(INK).strong());
    ui.add_space(4.0);
    muted(ui, subtitle);
    ui.add_space(18.0);
}

/// Money text uses a monospace font so digits are tabular (fixed width).
pub fn money_text(value: f64, size: f32, color: Color32) -> RichText {
    RichText::new(format_inr(value))
        .font(FontId::new(size, FontFamily::Monospace))
        .color(color)
        .strong()
}

pub fn money(ui: &mut Ui, value: f64, size: f32) -> Response {
    ui.label(money_text(value, size, INK))
}

pub fn badge(ui: &mut Ui, text: impl Into<String>, subtle: bool) -> Response {
    let (fill, color) = if subtle {
        (SUBTLE, MUTED)
    } else {
        (INK, WHITE)
    };
    Frame::new()
        .fill(fill)
        .corner_radius(CornerRadius::same(5))
        .inner_margin(Margin::symmetric(8, 3))
        .show(ui, |ui| {
            ui.label(RichText::new(text).size(10.5).color(color).strong());
        })
        .response
}

pub fn kpi(ui: &mut Ui, label: &str, value: &str, hint: &str, is_money: bool) {
    card(ui, |ui| {
        ui.label(RichText::new(label).size(12.5).color(MUTED).strong());
        ui.add_space(10.0);
        if is_money {
            ui.label(money_text(value.parse::<f64>().unwrap_or(0.0), 20.0, INK));
        } else {
            ui.label(RichText::new(value).size(20.0).color(INK).strong());
        }
        ui.add_space(4.0);
        caption(ui, hint);
    });
}

pub fn field_label(ui: &mut Ui, text: &str) {
    ui.label(RichText::new(text).size(11.5).color(MUTED).strong());
    ui.add_space(3.0);
}

pub fn divider(ui: &mut Ui) {
    ui.add_space(6.0);
    ui.separator();
    ui.add_space(6.0);
}

/// Standard "Showing x–y of z" footer with Previous / Next buttons.
#[allow(clippy::too_many_arguments)]
pub fn pagination(
    ui: &mut Ui,
    offset: &mut i64,
    limit: i64,
    total: i64,
    id: &str,
) -> bool {
    let mut changed = false;
    if total <= 0 {
        return changed;
    }
    let page = *offset / limit.max(1);
    let pages = (total + limit - 1) / limit.max(1);
    ui.add_space(8.0);
    ui.separator();
    ui.horizontal(|ui| {
        muted(
            ui,
            format!(
                "Showing {}–{} of {}  ·  page {} of {}",
                *offset + 1,
                (*offset + limit).min(total),
                total,
                page + 1,
                pages
            ),
        );
        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            if ui.add_enabled(*offset + limit < total, egui::Button::new("Next")).clicked() {
                *offset += limit;
                changed = true;
            }
            if ui.add_enabled(*offset > 0, egui::Button::new("Prev")).clicked() {
                *offset = (*offset - limit).max(0);
                changed = true;
            }
            let _ = id;
        });
    });
    changed
}

pub fn empty_state(ui: &mut Ui, title: &str, detail: &str) {
    ui.vertical_centered(|ui| {
        ui.add_space(30.0);
        ui.label(RichText::new(title).size(14.0).color(INK).strong());
        ui.add_space(4.0);
        muted(ui, detail);
        ui.add_space(30.0);
    });
}

pub fn money_or_dash(v: Option<f64>) -> String {
    v.map(format_inr).unwrap_or_else(|| "—".to_string())
}

pub fn style_override_text(ui: &mut Ui, text: &str, style: TextStyle) -> Response {
    ui.label(RichText::new(text).text_style(style))
}
