//! BillFlow visual identity.
//!
//! Jet black + soft white + a single flame-orange accent. There are no other
//! chromatic accents, no gradients and no card shadows.

use std::sync::Arc;

use egui::{
    Color32, Context, FontData, FontDefinitions, FontFamily, FontId, Margin, Stroke, Style,
    Visuals,
};
use egui::style::{WidgetVisuals, Widgets};

pub const INK: Color32 = Color32::from_rgb(0x0A, 0x0A, 0x0A);
pub const WHITE: Color32 = Color32::from_rgb(0xFF, 0xFF, 0xFF);
pub const CANVAS: Color32 = Color32::from_rgb(0xF7, 0xF5, 0xF0);
pub const ORANGE: Color32 = Color32::from_rgb(0xFF, 0x6A, 0x00);
pub const MUTED: Color32 = Color32::from_rgb(0x6B, 0x68, 0x62);
pub const BORDER: Color32 = Color32::from_rgb(0xE4, 0xE0, 0xD8);
pub const SUBTLE: Color32 = Color32::from_rgb(0xEF, 0xEC, 0xE5);
pub const ON_DARK: Color32 = Color32::from_rgb(0xF7, 0xF5, 0xF0);
pub const ON_DARK_MUTED: Color32 = Color32::from_rgb(0xB8, 0xB3, 0xAA);

pub const RADIUS: u8 = 8;
pub const RADIUS_SM: u8 = 6;

/// Install a system sans font when available so the rupee glyph (₹) and other
/// currency symbols render correctly. Falls back to egui's embedded fonts.
pub fn configure_fonts(ctx: &Context) {
    const SANS_PATHS: &[&str] = &[
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/Library/Fonts/Arial.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ];
    const MONO_PATHS: &[&str] = &[
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf",
        "C:\\Windows\\Fonts\\consola.ttf",
    ];

    let sans = SANS_PATHS.iter().find_map(|p| std::fs::read(p).ok());
    let mono = MONO_PATHS.iter().find_map(|p| std::fs::read(p).ok());
    if sans.is_none() && mono.is_none() {
        return;
    }

    let mut fonts = FontDefinitions::default();
    if let Some(data) = sans {
        fonts.font_data.insert(
            "BillFlow Sans".to_owned(),
            Arc::new(FontData::from_owned(data)),
        );
        if let Some(family) = fonts.families.get_mut(&FontFamily::Proportional) {
            family.insert(0, "BillFlow Sans".to_owned());
        }
    }
    if let Some(data) = mono {
        fonts.font_data.insert(
            "BillFlow Mono".to_owned(),
            Arc::new(FontData::from_owned(data)),
        );
        if let Some(family) = fonts.families.get_mut(&FontFamily::Monospace) {
            family.insert(0, "BillFlow Mono".to_owned());
        }
    }
    ctx.set_fonts(fonts);
}

/// Apply the global widget style once at start-up.
pub fn apply(ctx: &Context) {
    let mut style: Style = (*ctx.style()).clone();
    let mut visuals = Visuals::light();

    visuals.override_text_color = Some(INK);
    visuals.panel_fill = CANVAS;
    visuals.window_fill = WHITE;
    visuals.window_stroke = Stroke::new(1.0_f32, BORDER);
    visuals.extreme_bg_color = WHITE;
    visuals.faint_bg_color = SUBTLE;
    visuals.code_bg_color = SUBTLE;
    visuals.hyperlink_color = ORANGE;
    visuals.selection.bg_fill = ORANGE;
    visuals.selection.stroke = Stroke::new(1.0_f32, ORANGE);
    visuals.widgets = widget_style();

    style.visuals = visuals;
    style.spacing.item_spacing = egui::vec2(8.0, 7.0);
    style.spacing.button_padding = egui::vec2(12.0, 7.0);
    style.spacing.window_margin = Margin::same(0);
    style.text_styles.insert(
        egui::TextStyle::Body,
        FontId::new(13.5, FontFamily::Proportional),
    );
    style.text_styles.insert(
        egui::TextStyle::Button,
        FontId::new(13.0, FontFamily::Proportional),
    );
    style.text_styles.insert(
        egui::TextStyle::Heading,
        FontId::new(21.0, FontFamily::Proportional),
    );
    ctx.set_style(style);
}

fn widget_style() -> Widgets {
    fn base(bg: Color32, weak: Color32, stroke: Stroke, fg: Color32) -> WidgetVisuals {
        WidgetVisuals {
            bg_fill: bg,
            weak_bg_fill: weak,
            bg_stroke: stroke,
            corner_radius: egui::CornerRadius::same(RADIUS),
            fg_stroke: Stroke::new(1.0_f32, fg),
            expansion: 1.5,
        }
    }

    Widgets {
        noninteractive: base(WHITE, SUBTLE, Stroke::NONE, MUTED),
        inactive: base(WHITE, SUBTLE, Stroke::new(1.0_f32, BORDER), INK),
        hovered: base(WHITE, SUBTLE, Stroke::new(1.0_f32, ORANGE), INK),
        active: base(SUBTLE, SUBTLE, Stroke::new(1.0_f32, ORANGE), INK),
        open: base(WHITE, SUBTLE, Stroke::new(1.0_f32, ORANGE), INK),
    }
}
