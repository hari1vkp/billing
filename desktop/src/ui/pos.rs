//! Staff point-of-sale: dark top bar, scanner + catalogue, and the cart rail.

use billflow_shared::models::Product;
use billflow_shared::services::inventory;
use egui::{
    Align, Align2, Color32, Context, FontId, Frame, Layout, Margin, Response, CornerRadius, Sense,
    Stroke, TextEdit, Ui, Vec2, Widget,
};

use crate::app::App;
use crate::theme::*;
use crate::ui::widgets as w;

const BARCODE_ID: &str = "pos_barcode";

#[derive(Clone, Debug)]
pub struct PosState {
    pub refresh_needed: bool,
    pub barcode: String,
    pub select_barcode: bool,
    pub search_query: String,
    pub products: Vec<Product>,
    pub customers: Vec<billflow_shared::models::Customer>,
    pub cart: Vec<billflow_shared::services::billing::CartLine>,
    pub customer_query: String,
    pub customer_id: Option<String>,
    pub customer_name: String,
    pub customer_open: bool,
    pub invoice_discount: String,
    pub show_stock: bool,
    pub stock_query: String,
    pub stock_low_only: bool,
    pub adjust_id: Option<String>,
    pub adjust_delta: String,
    pub adjust_reason: String,
    pub adjust_notes: String,
    #[allow(dead_code)]
    pub stock_page: i64,
}

impl Default for PosState {
    fn default() -> Self {
        Self {
            refresh_needed: false,
            barcode: String::new(),
            select_barcode: false,
            search_query: String::new(),
            products: Vec::new(),
            customers: Vec::new(),
            cart: Vec::new(),
            customer_query: String::new(),
            customer_id: None,
            customer_name: "Walk-in Customer".to_string(),
            customer_open: false,
            invoice_discount: "0".to_string(),
            show_stock: false,
            stock_query: String::new(),
            stock_low_only: false,
            adjust_id: None,
            adjust_delta: String::new(),
            adjust_reason: "correction".to_string(),
            adjust_notes: String::new(),
            stock_page: 0,
        }
    }
}

/* ------------------------------- top bar --------------------------------- */

pub fn top_bar(app: &mut App, ctx: &Context) {
    egui::TopBottomPanel::top("pos_topbar")
        .exact_height(58.0)
        .frame(Frame::new().fill(INK))
        .show(ctx, |ui| {
            ui.horizontal_centered(|ui| {
                ui.add_space(18.0);
                small_mark(ui);
                ui.add_space(9.0);
                ui.label(
                    egui::RichText::new("BillFlow")
                        .size(15.0)
                        .color(ON_DARK)
                        .strong(),
                );
                ui.add_space(16.0);
                ui.label(egui::RichText::new("|").color(egui::Color32::from_rgba_unmultiplied(0xF7, 0xF5, 0xF0, 36)));
                ui.add_space(14.0);
                let business = app
                    .business
                    .as_ref()
                    .map(|b| b.name.clone())
                    .unwrap_or_else(|| "My Business".to_string());
                ui.label(egui::RichText::new(business).size(12.5).color(ON_DARK_MUTED));
                ui.add_space(8.0);
                Frame::new()
                    .fill(egui::Color32::from_rgba_unmultiplied(0xF7, 0xF5, 0xF0, 28))
                    .corner_radius(CornerRadius::same(5))
                    .inner_margin(Margin::symmetric(7, 3))
                    .show(ui, |ui| {
                        ui.label(egui::RichText::new("POS").size(10.0).color(ON_DARK_MUTED).strong());
                    });

                ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                    let name = app
                        .user
                        .as_ref()
                        .map(|u| u.full_name.clone())
                        .unwrap_or_else(|| "User".to_string());
                    if dark_link(ui, "Sign out").clicked() {
                        app.logout();
                    }
                    ui.label(
                        egui::RichText::new(format!("{}  ·  {}", name, app.currency()))
                            .size(11.5)
                            .color(ON_DARK_MUTED),
                    );
                    ui.add_space(8.0);
                    if dark_link(ui, "Stock").clicked() {
                        app.pos.show_stock = true;
                    }
                    if app.is_owner() {
                        if dark_link(ui, "Admin").clicked() {
                            app.open_admin();
                        }
                    }
                    if w::primary(ui, "+  New Bill").clicked() {
                        app.clear_cart();
                        app.pos.show_stock = false;
                        app.barcode_focus_requested = true;
                    }
                });
            });
        });
}

fn dark_link(ui: &mut Ui, text: &str) -> Response {
    ui.add(
        egui::Button::new(
            egui::RichText::new(text)
                .size(12.5)
                .color(ON_DARK_MUTED),
        )
        .fill(Color32::TRANSPARENT)
        .stroke(Stroke::NONE)
        .corner_radius(CornerRadius::same(RADIUS_SM)),
    )
}

fn small_mark(ui: &mut Ui) {
    Frame::new()
        .fill(ORANGE)
        .corner_radius(CornerRadius::same(8))
        .inner_margin(Margin::symmetric(7, 6))
        .show(ui, |ui| {
            ui.label(egui::RichText::new("▤").size(15.0).color(WHITE).strong());
        });
}

/* -------------------------------- main ----------------------------------- */

pub fn ui(app: &mut App, ctx: &Context) {
    if app.pos.show_stock {
        stock_screen(app, ctx);
        return;
    }

    cart_panel(app, ctx);
    main_panel(app, ctx);
}

fn main_panel(app: &mut App, ctx: &Context) {
    // F2 and keyboard-wedge support: keep the scanner input as the default
    // focus target so a wedge scanner's keystrokes always land there.
    if ctx.input_mut(|i| i.consume_key(egui::Modifiers::NONE, egui::Key::F2)) {
        app.barcode_focus_requested = true;
    }

    let barcode_id = egui::Id::new(BARCODE_ID);
    if app.checkout.is_none() {
        wedge_characters(app, ctx, barcode_id);
    }

    egui::CentralPanel::default()
        .frame(Frame::new().fill(CANVAS))
        .show(ctx, |ui| {
            if app.barcode_focus_requested {
                ui.memory_mut(|m| m.request_focus(barcode_id));
                app.barcode_focus_requested = false;
            }
            if app.pos.select_barcode {
                ui.memory_mut(|m| m.request_focus(barcode_id));
                app.pos.select_barcode = false;
            }

            ui.vertical(|ui| {
                barcode_card(app, ui, barcode_id);
                ui.add_space(14.0);
                catalog(app, ui);
            });
        });
}

fn wedge_characters(app: &mut App, ctx: &Context, barcode_id: egui::Id) {
    let focused = ctx.memory(|m| m.focused());
    let mut typed = String::new();
    let mut has_modifiers = false;
    ctx.input(|i| {
        has_modifiers = i.modifiers.ctrl || i.modifiers.alt || i.modifiers.mac_cmd;
        for event in &i.events {
            if let egui::Event::Text(text) = event {
                if text.chars().count() == 1 {
                    typed.push_str(text);
                }
            }
        }
    });
    if focused.is_none() && !typed.is_empty() && !has_modifiers {
        app.pos.barcode.push_str(&typed);
        ctx.memory_mut(|m| m.request_focus(barcode_id));
        ctx.input_mut(|i| {
            i.events.retain(|e| !matches!(e, egui::Event::Text(_)));
        });
    }
}

fn barcode_card(app: &mut App, ui: &mut Ui, barcode_id: egui::Id) {
    w::flat_card(ui, |ui| {
        ui.horizontal(|ui| {
            ui.add_space(12.0);
            Frame::new()
                .fill(SUBTLE)
                .corner_radius(CornerRadius::same(10))
                .inner_margin(Margin::same(12))
                .show(ui, |ui| {
                    ui.label(egui::RichText::new("▥").size(24.0).color(INK).strong());
                });
            ui.add_space(10.0);
            ui.vertical(|ui| {
                ui.label(
                    egui::RichText::new("Scan barcode or type and press Enter")
                        .size(12.5)
                        .color(INK)
                        .strong(),
                );
                ui.add_space(7.0);
                ui.horizontal(|ui| {
                    let enter = ui.input(|i| i.key_pressed(egui::Key::Enter));
                    let focused = ui.memory(|m| m.has_focus(barcode_id));
                    if enter && focused && !app.pos.barcode.trim().is_empty() {
                        app.barcode_lookup();
                    }
                    let response = ui.add_sized(
                        [ui.available_width() - 96.0, 46.0],
                        TextEdit::singleline(&mut app.pos.barcode)
                            .id(barcode_id)
                            .hint_text("Scan or enter product barcode…")
                            .font(FontId::new(16.0, egui::FontFamily::Proportional))
                            .desired_width(ui.available_width() - 96.0),
                    );
                    if response.has_focus() {
                        ui.painter().rect_stroke(
                            response.rect.expand(1.0),
                            CornerRadius::same(RADIUS_SM),
                            Stroke::new(1.5_f32, ORANGE),
                            egui::StrokeKind::Middle,
                        );
                    }
                    if !app.pos.barcode.is_empty() && w::ghost(ui, "Clear").clicked() {
                        app.pos.barcode.clear();
                        app.barcode_focus_requested = true;
                    }
                    Frame::new()
                        .fill(SUBTLE)
                        .corner_radius(CornerRadius::same(5))
                        .inner_margin(Margin::symmetric(6, 4))
                        .show(ui, |ui| {
                            ui.label(egui::RichText::new("F2").size(10.5).color(MUTED));
                        });
                });
            });
            ui.add_space(12.0);
        });
    });
}

fn catalog(app: &mut App, ui: &mut Ui) {
    w::flat_card(ui, |ui| {
        ui.horizontal(|ui| {
            ui.add_space(14.0);
            ui.vertical(|ui| {
                let title = if app.pos.search_query.trim().is_empty() {
                    "Popular products".to_string()
                } else {
                    format!("Results for \"{}\"", app.pos.search_query.trim())
                };
                ui.label(egui::RichText::new(title).size(15.0).color(INK).strong());
                w::muted(ui, "Click a product to add it to the current bill");
            });
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                let mut changed = false;
                let response = ui.add_sized(
                    [230.0, 34.0],
                    TextEdit::singleline(&mut app.pos.search_query)
                        .hint_text("Search products or barcode…")
                        .desired_width(230.0),
                );
                changed |= response.changed();
                if changed {
                    app.search_products();
                }
            });
            ui.add_space(14.0);
        });
        ui.separator();

        let mut products: Vec<Product> = app.pos.products.clone();
        products.sort_by(|a, b| a.name.cmp(&b.name));

        egui::ScrollArea::vertical()
            .id_salt("product_grid")
            .auto_shrink([false, false])
            .show(ui, |ui| {
                if products.is_empty() {
                    w::empty_state(ui, "No products found", "Try a different name or barcode.");
                    return;
                }
                let spacing = 12.0;
                let columns = ((ui.available_width() + spacing) / (176.0 + spacing)).max(1.0) as usize;
                let tile_w = (ui.available_width() - spacing * (columns - 1) as f32)
                    / columns as f32;
                for row in products.chunks(columns) {
                    ui.horizontal(|ui| {
                        for product in row {
                            if product_tile(ui, product, tile_w).clicked() {
                                let name = product.name.clone();
                                app.add_to_cart(product.clone());
                                app.set_status(format!("{} added to bill", name), false);
                            }
                        }
                    });
                    ui.add_space(spacing);
                }
            });
    });
}

struct ProductTile<'a> {
    product: &'a Product,
    width: f32,
}

impl Widget for ProductTile<'_> {
    fn ui(self, ui: &mut Ui) -> Response {
        let (rect, response) = ui.allocate_exact_size(Vec2::new(self.width, 132.0), Sense::click());
        let fill = if response.hovered() { SUBTLE } else { WHITE };
        let stroke = if response.hovered() || response.has_focus() {
            Stroke::new(1.5_f32, ORANGE)
        } else {
            Stroke::new(1.0_f32, BORDER)
        };
        ui.painter().rect(
            rect,
            CornerRadius::same(RADIUS),
            fill,
            stroke,
            egui::StrokeKind::Inside,
        );

        let left = rect.left() + 13.0;
        let mut y = rect.top() + 12.0;
        ui.painter().text(
            egui::pos2(left, y + 8.0),
            Align2::LEFT_TOP,
            "▣",
            FontId::new(15.0, egui::FontFamily::Proportional),
            INK,
        );
        y += 26.0;

        let name = truncate(&self.product.name, 20);
        ui.painter().text(
            egui::pos2(left, y),
            Align2::LEFT_TOP,
            name,
            FontId::new(13.0, egui::FontFamily::Proportional),
            INK,
        );
        y += 18.0;

        let meta = truncate(
            self.product
                .barcode
                .as_deref()
                .filter(|s| !s.is_empty())
                .unwrap_or(&self.product.sku),
            20,
        );
        ui.painter().text(
            egui::pos2(left, y),
            Align2::LEFT_TOP,
            meta,
            FontId::new(10.5, egui::FontFamily::Proportional),
            MUTED,
        );
        y += 18.0;

        let price = billflow_shared::money::format_inr(self.product.price).replace('₹', "Rs. ");
        ui.painter().text(
            egui::pos2(left, y),
            Align2::LEFT_TOP,
            price,
            FontId::new(13.0, egui::FontFamily::Monospace),
            INK,
        );
        ui.painter().text(
            egui::pos2(rect.right() - 13.0, y),
            Align2::RIGHT_TOP,
            format!("{}% GST", self.product.gst_rate),
            FontId::new(10.0, egui::FontFamily::Proportional),
            MUTED,
        );
        y += 20.0;

        let low = !self.product.is_service
            && self.product.stock <= self.product.low_stock_threshold;
        let stock_text = if self.product.is_service {
            "Service".to_string()
        } else {
            format!("Stock: {}", self.product.stock)
                + if low { "  ·  Low" } else { "" }
        };
        ui.painter().text(
            egui::pos2(left, y),
            Align2::LEFT_TOP,
            stock_text,
            FontId::new(10.5, egui::FontFamily::Proportional),
            if low { INK } else { MUTED },
        );
        response
    }
}

fn product_tile<'a>(ui: &mut Ui, product: &'a Product, width: f32) -> Response {
    ui.add(ProductTile { product, width })
}

fn truncate(text: &str, max: usize) -> String {
    if text.chars().count() <= max {
        text.to_string()
    } else {
        let prefix: String = text.chars().take(max.saturating_sub(1)).collect();
        format!("{}…", prefix)
    }
}

/* -------------------------------- cart ----------------------------------- */

pub fn cart_panel(app: &mut App, ctx: &Context) {
    let frame = Frame::new()
        .fill(WHITE)
        .stroke(Stroke::new(1.0_f32, BORDER))
        .inner_margin(Margin::symmetric(18, 16));
    egui::SidePanel::right("pos_cart")
        .exact_width(400.0)
        .resizable(false)
        .frame(frame)
        .show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.vertical(|ui| {
                    ui.label(egui::RichText::new("Current bill").size(16.0).color(INK).strong());
                    let units: f64 = app.pos.cart.iter().map(|l| l.quantity).sum();
                    w::muted(ui, format!("{} item{} in cart", units, if units == 1.0 { "" } else { "s" }));
                });
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                    if !app.pos.cart.is_empty() && w::ghost(ui, "Clear").clicked() {
                        app.clear_cart();
                    }
                });
            });
            ui.add_space(12.0);

            customer_selector(app, ui);
            ui.add_space(12.0);
            ui.separator();

            let cart_empty = app.pos.cart.is_empty();
            egui::ScrollArea::vertical()
                .id_salt("cart_lines")
                .auto_shrink([false, true])
                .max_height((ui.available_height() - 250.0).max(120.0))
                .show(ui, |ui| {
                    if cart_empty {
                        w::empty_state(ui, "Your cart is empty", "Scan a barcode or tap a product to begin.");
                    } else {
                        let ids: Vec<String> = app.pos.cart.iter().map(|l| l.product.id.clone()).collect();
                        for id in ids {
                            cart_row(app, ui, &id);
                        }
                    }
                });

            ui.with_layout(Layout::bottom_up(Align::TOP), |ui| {
                // bottom_up: the first item added sits at the bottom.
                let hint = if app.pos.cart.is_empty() {
                    "Add at least one item to continue to payment."
                } else {
                    "UPI QR or cash — one step to complete the sale."
                };
                w::caption(ui, hint);
                let totals = app.cart_totals();
                let button = w::primary(
                    ui,
                    format!("Proceed to Payment · {}", app.money(totals.total)),
                );
                if button.clicked() {
                    app.open_checkout(ctx);
                }
                ui.add_space(10.0);
                totals_block(app, ui);
            });
        });
}

fn customer_selector(app: &mut App, ui: &mut Ui) {
    w::field_label(ui, "Customer");
    let response = ui.add_sized(
        [ui.available_width(), 34.0],
        TextEdit::singleline(&mut app.pos.customer_query)
            .hint_text("Search customer…")
            .desired_width(ui.available_width()),
    );
    if response.clicked() {
        app.pos.customer_open = true;
    }
    w::caption(ui, format!("Selected: {}", app.pos.customer_name));

    if app.pos.customer_open {
        Frame::new()
            .fill(WHITE)
            .stroke(Stroke::new(1.0_f32, BORDER))
            .corner_radius(CornerRadius::same(RADIUS_SM))
            .inner_margin(Margin::same(6))
            .show(ui, |ui| {
                egui::ScrollArea::vertical().max_height(200.0).show(ui, |ui| {
                    if ui.add_sized([ui.available_width(), 28.0], egui::Button::new(
                        egui::RichText::new("Walk-in Customer").size(12.0).color(INK),
                    ).fill(Color32::TRANSPARENT).stroke(Stroke::NONE)).clicked()
                    {
                        app.pos.customer_id = None;
                        app.pos.customer_name = "Walk-in Customer".to_string();
                        app.pos.customer_query.clear();
                        app.pos.customer_open = false;
                    }
                    let query = app.pos.customer_query.trim().to_lowercase();
                    let list: Vec<_> = app
                        .pos
                        .customers
                        .iter()
                        .filter(|c| {
                            query.is_empty()
                                || c.name.to_lowercase().contains(&query)
                                || c.phone.to_lowercase().contains(&query)
                                || c.email.to_lowercase().contains(&query)
                        })
                        .take(30)
                        .cloned()
                        .collect();
                    for customer in list {
                        if ui.add_sized([ui.available_width(), 28.0], egui::Button::new(
                            egui::RichText::new(format!("{}  ·  {}", customer.name, customer.phone))
                                .size(12.0)
                                .color(INK),
                        ).fill(Color32::TRANSPARENT).stroke(Stroke::NONE)).clicked()
                        {
                            app.pos.customer_id = Some(customer.id.clone());
                            app.pos.customer_name = customer.name.clone();
                            app.pos.customer_query = customer.name.clone();
                            app.pos.customer_open = false;
                        }
                    }
                });
            });
    }
}

fn cart_row(app: &mut App, ui: &mut Ui, id: &str) {
    let Some(index) = app.pos.cart.iter().position(|l| l.product.id == id) else { return };
    let line = app.pos.cart[index].clone();
    let base = line.product.price * line.quantity;
    let discount = base * (line.discount_percent / 100.0);
    let line_total = (base - discount) * (1.0 + line.product.gst_rate / 100.0);

    Frame::new()
        .fill(WHITE)
        .stroke(Stroke::new(1.0_f32, BORDER))
        .corner_radius(CornerRadius::same(RADIUS_SM))
        .inner_margin(Margin::symmetric(11, 10))
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.vertical(|ui| {
                    ui.label(egui::RichText::new(&line.product.name).size(13.0).color(INK).strong());
                    w::caption(
                        ui,
                        format!("{} · {}% GST", app.money(line.product.price), line.product.gst_rate),
                    );
                });
                ui.with_layout(Layout::right_to_left(Align::TOP), |ui| {
                    if w::ghost(ui, "×").clicked() {
                        app.pos.cart.remove(index);
                        return;
                    }
                });
            });
            ui.add_space(6.0);
            ui.horizontal(|ui| {
                if w::small_button(ui, "−").clicked() {
                    app.pos.cart[index].quantity = (app.pos.cart[index].quantity - 1.0).max(0.0);
                    if app.pos.cart[index].quantity <= 0.0 {
                        app.pos.cart.remove(index);
                        return;
                    }
                }
                Frame::new()
                    .fill(SUBTLE)
                    .corner_radius(CornerRadius::same(RADIUS_SM))
                    .inner_margin(Margin::symmetric(9, 4))
                    .show(ui, |ui| {
                        ui.label(
                            egui::RichText::new(format!("{}", line.quantity))
                                .font(FontId::new(12.0, egui::FontFamily::Monospace))
                                .color(INK),
                        );
                    });
                if w::small_button(ui, "+").clicked() {
                    app.pos.cart[index].quantity += 1.0;
                }
                ui.add_space(4.0);
                w::caption(ui, "Disc %");
                let mut disc = app.pos.cart[index].discount_percent.to_string();
                if ui.add_sized([42.0, 26.0], TextEdit::singleline(&mut disc)).changed() {
                    app.pos.cart[index].discount_percent = disc.parse::<f64>().unwrap_or(0.0).clamp(0.0, 100.0);
                }
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                    ui.label(
                        egui::RichText::new(app.money(line_total))
                            .font(FontId::new(13.0, egui::FontFamily::Monospace))
                            .color(INK)
                            .strong(),
                    );
                });
            });
        });
    ui.add_space(8.0);
}

fn totals_block(app: &mut App, ui: &mut Ui) {
    let totals = app.cart_totals();
    w::section_title(ui, "Bill summary", None);
    ui.add_space(6.0);
    total_row(ui, "Subtotal", app.money(totals.subtotal), false);
    total_row(ui, "Item discounts", format!("− {}", app.money(totals.discount)), false);
    total_row(ui, "GST", app.money(totals.tax), false);

    ui.horizontal(|ui| {
        w::caption(ui, "Invoice discount (%)");
        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            let mut disc = app.pos.invoice_discount.clone();
            let response = ui.add_sized([54.0, 28.0], TextEdit::singleline(&mut disc));
            if response.changed() {
                app.pos.invoice_discount = disc;
            }
            let d = app.cart_totals().discount;
            ui.label(
                egui::RichText::new(format!("− {}", app.money(d)))
                    .font(FontId::new(12.0, egui::FontFamily::Monospace))
                    .color(INK),
            );
        });
    });
    ui.add_space(4.0);
    ui.separator();
    ui.add_space(4.0);
    ui.horizontal(|ui| {
        ui.label(egui::RichText::new("Grand total").size(13.0).color(INK).strong());
        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            ui.label(w::money_text(totals.total, 20.0, INK));
        });
    });
}

fn total_row(ui: &mut Ui, label: &str, value: String, strong: bool) {
    ui.horizontal(|ui| {
        w::muted(ui, label);
        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            ui.label(
                egui::RichText::new(value)
                    .font(FontId::new(12.0, egui::FontFamily::Monospace))
                    .color(INK)
                    .strong(),
            );
            let _ = strong;
        });
    });
}

/* ------------------------------- stock view ------------------------------- */

fn stock_screen(app: &mut App, ctx: &Context) {
    egui::CentralPanel::default()
        .frame(Frame::new().fill(CANVAS))
        .show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.label(egui::RichText::new("Stock").size(21.0).color(INK).strong());
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                    if w::secondary(ui, "Back to billing").clicked() {
                        app.pos.show_stock = false;
                        app.barcode_focus_requested = true;
                    }
                });
            });
            w::muted(ui, "Live stock levels and quick adjustments");
            ui.add_space(16.0);

            w::card(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.add_sized(
                        [240.0, 32.0],
                        TextEdit::singleline(&mut app.pos.stock_query).hint_text("Search products…"),
                    );
                    let low = &mut app.pos.stock_low_only;
                    if ui.checkbox(low, "Low stock only").clicked() {
                        // filter applied below
                    }
                });
                ui.add_space(10.0);
                ui.separator();

                let query = app.pos.stock_query.to_lowercase();
                let products: Vec<_> = app
                    .pos
                    .products
                    .iter()
                    .filter(|p| {
                        let matches = query.is_empty()
                            || p.name.to_lowercase().contains(&query)
                            || p.sku.to_lowercase().contains(&query);
                        let low = p.stock <= p.low_stock_threshold;
                        matches && (!app.pos.stock_low_only || low)
                    })
                    .cloned()
                    .collect();

                egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
                    egui::Grid::new("stock_grid")
                        .num_columns(5)
                        .spacing([12.0, 8.0])
                        .striped(true)
                        .show(ui, |ui| {
                            ui.label(egui::RichText::new("Product").strong());
                            ui.label(egui::RichText::new("SKU").strong());
                            ui.label(egui::RichText::new("Stock").strong());
                            ui.label(egui::RichText::new("Threshold").strong());
                            ui.label("");
                            ui.end_row();
                            for product in products {
                                ui.label(product.name);
                                ui.label(product.sku);
                                ui.label(if product.is_service { "Service".to_string() } else { format!("{}", product.stock) });
                                ui.label(format!("{}", product.low_stock_threshold));
                                if w::link(ui, "Adjust").clicked() {
                                    app.pos.adjust_id = Some(product.id);
                                    app.pos.adjust_delta.clear();
                                    app.pos.adjust_notes.clear();
                                    app.pos.adjust_reason = "correction".to_string();
                                }
                                ui.end_row();
                            }
                        });
                });
            });
        });

    if app.pos.adjust_id.is_some() {
        adjust_modal(app, ctx);
    }
}

#[allow(deprecated)] // egui 0.31 ComboBox::from_id_source has no replacement yet
fn adjust_modal(app: &mut App, ctx: &Context) {
    let Some(product_id) = app.pos.adjust_id.clone() else { return };
    let product_name = app
        .pos
        .products
        .iter()
        .find(|p| p.id == product_id)
        .map(|p| p.name.clone())
        .unwrap_or_else(|| "Product".to_string());
    let business_id = app.business_id().unwrap_or_default();
    let user_id = app.user_id().unwrap_or_default();

    egui::Window::new("Adjust stock")
        .collapsible(false)
        .resizable(false)
        .anchor(Align2::CENTER_CENTER, Vec2::ZERO)
        .show(ctx, |ui| {
            ui.set_width(340.0);
            ui.label(egui::RichText::new(product_name).size(15.0).color(INK).strong());
            ui.add_space(10.0);
            w::field_label(ui, "Change (+ to add / − to remove)");
            ui.add_sized([ui.available_width(), 34.0], TextEdit::singleline(&mut app.pos.adjust_delta).hint_text("e.g. -5"));
            ui.add_space(8.0);
            w::field_label(ui, "Reason");
            egui::ComboBox::from_id_source("stock_reason")
                .selected_text(app.pos.adjust_reason.clone())
                .show_ui(ui, |ui| {
                    for reason in ["found", "damaged", "return", "correction"] {
                        ui.selectable_value(&mut app.pos.adjust_reason, reason.to_string(), reason);
                    }
                });
            ui.add_space(8.0);
            w::field_label(ui, "Notes (optional)");
            ui.add_sized([ui.available_width(), 34.0], TextEdit::singleline(&mut app.pos.adjust_notes));
            ui.add_space(14.0);
            ui.horizontal(|ui| {
                if w::secondary(ui, "Cancel").clicked() {
                    app.pos.adjust_id = None;
                }
                if w::primary(ui, "Apply").clicked() {
                    let delta = app.pos.adjust_delta.parse::<f64>().unwrap_or(0.0);
                    let notes = app.pos.adjust_notes.trim();
                    let notes = if notes.is_empty() { None } else { Some(notes) };
                    let result = {
                        let conn = app.db.conn();
                        inventory::adjust_stock(
                            &conn,
                            &business_id,
                            &user_id,
                            &product_id,
                            delta,
                            &app.pos.adjust_reason,
                            notes,
                            app.is_owner(),
                        )
                    };
                    match result {
                        Ok(_) => {
                            app.set_status("Stock adjusted", false);
                            app.pos.adjust_id = None;
                            app.pos.refresh_needed = true;
                        }
                        Err(e) => app.show_error("Could not adjust stock", e),
                    }
                }
            });
        });
}
