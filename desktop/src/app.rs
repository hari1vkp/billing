//! Application state and all calls into the `billflow_shared` services.

use billflow_shared::db::Database;
use billflow_shared::money::format_inr;
use billflow_shared::models::{Business, PaymentMethod, Product, User};
use billflow_shared::repo;
use billflow_shared::services::{analytics::Analytics, billing, payments};
use egui::Context;

use crate::ui::admin::AdminState;
use crate::ui::checkout::{CheckoutState, PaymentTab};
use crate::ui::pos::PosState;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Screen {
    Login,
    Pos,
    Admin,
}

#[derive(Clone, Debug)]
pub struct Status {
    pub text: String,
    pub error: bool,
}

#[derive(Clone, Debug, Default)]
pub struct LoginState {
    pub email: String,
    pub password: String,
    pub show_password: bool,
}

#[derive(Clone, Debug)]
pub struct Receipt {
    pub amount: f64,
    pub invoice_number: String,
    pub method: PaymentMethod,
    pub note: String,
}

pub struct App {
    pub db: Database,
    pub screen: Screen,
    pub user: Option<User>,
    pub business: Option<Business>,
    pub status: Option<Status>,
    pub login: LoginState,
    pub pos: PosState,
    pub admin: AdminState,
    pub checkout: Option<CheckoutState>,
    pub qr_texture: Option<egui::TextureHandle>,
    pub barcode_focus_requested: bool,
}

impl App {
    pub fn new(db: Database) -> Self {
        Self {
            db,
            screen: Screen::Login,
            user: None,
            business: None,
            status: None,
            login: LoginState::default(),
            pos: PosState::default(),
            admin: AdminState::default(),
            checkout: None,
            qr_texture: None,
            barcode_focus_requested: true,
        }
    }

    /* ------------------------------ utilities ----------------------------- */

    pub fn set_status(&mut self, text: impl Into<String>, error: bool) {
        self.status = Some(Status {
            text: text.into(),
            error,
        });
    }

    pub fn clear_status(&mut self) {
        self.status = None;
    }

    pub fn business_id(&self) -> Option<String> {
        self.business.as_ref().map(|b| b.id.clone()).or_else(|| {
            self.user.as_ref().map(|u| u.business_id.clone())
        })
    }

    pub fn user_id(&self) -> Option<String> {
        self.user.as_ref().map(|u| u.id.clone())
    }

    pub fn is_owner(&self) -> bool {
        self.user
            .as_ref()
            .map(|u| billflow_shared::auth::is_owner(u))
            .unwrap_or(false)
    }

    pub fn currency(&self) -> String {
        self.business
            .as_ref()
            .map(|b| b.currency.clone())
            .unwrap_or_else(|| "INR".to_string())
    }

    pub fn money(&self, value: f64) -> String {
        let formatted = format_inr(value);
        // A few bundled fonts lack the rupee glyph; the fallback keeps money
        // readable without introducing a new colour or style.
        formatted.replace('₹', "Rs. ")
    }

    pub fn show_error(&mut self, context: &str, error: impl std::fmt::Display) {
        self.set_status(format!("{}: {}", context, error), true);
    }

    /* -------------------------------- auth -------------------------------- */

    pub fn fill_demo(&mut self) {
        self.login.email = "demo@billingapp.com".to_string();
        self.login.password = "Demo@1234".to_string();
        self.login.show_password = false;
    }

    pub fn login(&mut self) {
        let email = self.login.email.trim().to_string();
        let password = self.login.password.clone();
        if email.is_empty() || password.is_empty() {
            self.set_status("Enter your email and password", true);
            return;
        }

        let result = {
            let conn = self.db.conn();
            billflow_shared::auth::authenticate(&conn, &email, &password)
        };

        match result {
            Ok(user) => {
                let business = {
                    let conn = self.db.conn();
                    repo::get_business(&conn, &user.business_id)
                };
                match business {
                    Ok(business) => {
                        self.screen = if billflow_shared::auth::is_owner(&user) {
                            Screen::Admin
                        } else {
                            Screen::Pos
                        };
                        self.user = Some(user);
                        self.business = Some(business);
                        self.login.password.clear();
                        self.pos.refresh_needed = true;
                        self.admin.refresh_needed = true;
                        self.barcode_focus_requested = self.screen == Screen::Pos;
                        self.clear_status();
                    }
                    Err(e) => self.show_error("Could not load business", e),
                }
            }
            Err(e) => self.show_error("Sign in failed", e),
        }
    }

    pub fn logout(&mut self) {
        self.user = None;
        self.business = None;
        self.screen = Screen::Login;
        self.checkout = None;
        self.qr_texture = None;
        self.pos = PosState::default();
        self.admin = AdminState::default();
        self.login.password.clear();
        self.set_status("Signed out", false);
    }

    pub fn open_pos(&mut self) {
        if self.user.is_some() {
            self.screen = Screen::Pos;
            self.barcode_focus_requested = true;
            self.pos.refresh_needed = true;
        }
    }

    pub fn open_admin(&mut self) {
        if self.is_owner() {
            self.screen = Screen::Admin;
            self.admin.refresh_needed = true;
            self.checkout = None;
            self.qr_texture = None;
        } else {
            self.set_status("Only the owner can open the admin console", true);
        }
    }

    /* --------------------------------- POS --------------------------------- */

    pub fn refresh_pos(&mut self, ctx: &Context) {
        if !self.pos.refresh_needed {
            return;
        }
        self.pos.refresh_needed = false;

        let Some(business_id) = self.business_id() else { return };
        let query = self.pos.search_query.trim().to_string();

        let products = {
            let conn = self.db.conn();
            repo::list_products(&conn, &business_id, &query, false, 40, 0)
        };
        match products {
            Ok((items, _)) => self.pos.products = items.into_iter().filter(|p| p.is_active).collect(),
            Err(e) => self.show_error("Could not load products", e),
        }

        let customers = {
            let conn = self.db.conn();
            repo::list_customers(&conn, &business_id, "", 200, 0)
        };
        match customers {
            Ok((items, _)) => self.pos.customers = items.into_iter().filter(|c| c.is_active).collect(),
            Err(e) => self.show_error("Could not load customers", e),
        }
        ctx.request_repaint();
    }

    pub fn search_products(&mut self) {
        let Some(business_id) = self.business_id() else { return };
        let query = self.pos.search_query.trim().to_string();
        let result = {
            let conn = self.db.conn();
            repo::list_products(&conn, &business_id, &query, false, 40, 0)
        };
        match result {
            Ok((items, _)) => self.pos.products = items.into_iter().filter(|p| p.is_active).collect(),
            Err(e) => self.show_error("Product search failed", e),
        }
    }

    pub fn add_to_cart(&mut self, product: Product) {
        if let Some(line) = self.pos.cart.iter_mut().find(|l| l.product.id == product.id) {
            line.quantity += 1.0;
        } else {
            self.pos.cart.push(billing::CartLine {
                product,
                quantity: 1.0,
                discount_percent: 0.0,
            });
        }
        self.barcode_focus_requested = true;
    }

    pub fn barcode_lookup(&mut self) {
        let code = self.pos.barcode.trim().to_string();
        if code.is_empty() {
            return;
        }
        let Some(business_id) = self.business_id() else { return };

        let result = {
            let conn = self.db.conn();
            repo::get_product_by_barcode(&conn, &business_id, &code)
        };
        match result {
            Ok(Some(product)) => {
                let name = product.name.clone();
                self.add_to_cart(product);
                self.pos.barcode.clear();
                self.set_status(format!("{} added to bill", name), false);
            }
            Ok(None) => {
                self.set_status(format!("No product found for barcode \"{}\"", code), true);
                self.pos.select_barcode = true;
                self.barcode_focus_requested = true;
            }
            Err(e) => self.show_error("Barcode lookup failed", e),
        }
    }

    pub fn cart_totals(&self) -> billing::Totals {
        let discount = self
            .pos
            .invoice_discount
            .parse::<f64>()
            .unwrap_or(0.0)
            .clamp(0.0, 100.0);
        billing::calculate(&self.pos.cart, discount)
    }

    pub fn clear_cart(&mut self) {
        self.pos.cart.clear();
        self.pos.invoice_discount = "0".to_string();
        self.pos.customer_id = None;
        self.pos.customer_name = "Walk-in Customer".to_string();
        self.pos.customer_query.clear();
        self.pos.barcode.clear();
        self.barcode_focus_requested = true;
    }

    pub fn new_sale(&mut self) {
        self.clear_cart();
        self.checkout = None;
        self.qr_texture = None;
        if self.screen != Screen::Pos {
            self.screen = Screen::Pos;
        }
    }

    /* ------------------------------- checkout ------------------------------ */

    pub fn open_checkout(&mut self, ctx: &Context) {
        if self.pos.cart.is_empty() || self.checkout.is_some() {
            return;
        }
        let Some(business_id) = self.business_id() else { return };

        let invoice_number = {
            let conn = self.db.conn();
            repo::next_invoice_number(&conn, &business_id)
        };
        let invoice_number = match invoice_number {
            Ok(n) => n,
            Err(e) => {
                self.show_error("Could not prepare checkout", e);
                return;
            }
        };

        let total = self.cart_totals().total;
        let mut qr_error = None;
        self.qr_texture = None;

        if let Some(business) = &self.business {
            if !business.upi_id.trim().is_empty() {
                let uri = payments::build_upi_uri(
                    &business.upi_id,
                    &business.name,
                    total,
                    &invoice_number,
                    &business.currency,
                );
                match payments::qr_matrix(&uri) {
                    Ok((side, cells)) => {
                        let texture = build_qr_texture(ctx, side, &cells);
                        self.qr_texture = Some(texture);
                    }
                    Err(e) => {
                        qr_error = Some(format!("UPI QR unavailable: {}", e));
                    }
                }
            } else {
                qr_error = Some("UPI QR is not configured for this business.".to_string());
            }
        }

        self.checkout = Some(CheckoutState {
            invoice_number,
            tab: PaymentTab::Upi,
            total,
            qr_error,
            receipt: None,
            completing: false,
        });
        ctx.request_repaint();
    }

    pub fn close_checkout(&mut self) {
        self.checkout = None;
        self.qr_texture = None;
        self.barcode_focus_requested = true;
    }

    pub fn complete_sale(&mut self) {
        let (Some(checkout), Some(business_id), Some(user_id)) = (
            self.checkout.as_ref(),
            self.business_id(),
            self.user_id(),
        ) else {
            return;
        };
        if checkout.completing || checkout.receipt.is_some() {
            return;
        }

        let method = match checkout.tab {
            PaymentTab::Upi => PaymentMethod::Upi,
            PaymentTab::Cash => PaymentMethod::Cash,
        };
        let invoice_number = checkout.invoice_number.clone();
        let items: Vec<billing::CartItemInput> = self
            .pos
            .cart
            .iter()
            .map(|line| billing::CartItemInput {
                product_id: line.product.id.clone(),
                quantity: line.quantity,
                discount_percent: line.discount_percent,
            })
            .collect();
        let discount = self
            .pos
            .invoice_discount
            .parse::<f64>()
            .unwrap_or(0.0)
            .clamp(0.0, 100.0);
        let input = billing::CheckoutInput {
            pricing_mode: "retail".into(),
            customer_id: self.pos.customer_id.clone(),
            items,
            discount_percent: discount,
            transaction_ref: Some(invoice_number.clone()),
            method: method.clone(),
            notes: None,
        };

        let result = {
            let conn = self.db.conn();
            billing::checkout(&conn, &business_id, &user_id, input)
        };

        match result {
            Ok(result) => {
                let receipt = Receipt {
                    amount: result.invoice.total_amount,
                    invoice_number: result.invoice.invoice_number,
                    method: method.clone(),
                    note: result.payment.notes.clone().unwrap_or_else(|| {
                        "Payment manually confirmed by cashier".to_string()
                    }),
                };
                if let Some(checkout) = self.checkout.as_mut() {
                    checkout.receipt = Some(receipt);
                    checkout.completing = false;
                }
                self.qr_texture = None;
                self.clear_cart();
                self.pos.refresh_needed = true;
                self.admin.refresh_needed = true;
                self.set_status("Sale completed", false);
            }
            Err(e) => {
                if let Some(checkout) = self.checkout.as_mut() {
                    checkout.completing = false;
                }
                self.show_error("Could not complete sale", e);
            }
        }
    }

    /* -------------------------------- admin -------------------------------- */

    pub fn refresh_admin(&mut self, ctx: &Context) {
        if !self.admin.refresh_needed {
            return;
        }
        if !self.is_owner() {
            self.screen = Screen::Pos;
            return;
        }
        self.admin.refresh_needed = false;
        crate::ui::admin::reload(self, ctx);
        ctx.request_repaint();
    }
}

/// Build a nearest-filtered texture from the QR module matrix.
fn build_qr_texture(ctx: &Context, side: usize, cells: &[bool]) -> egui::TextureHandle {
    const SCALE: usize = 5;
    const QUIET: usize = 3;
    let modules = side + QUIET * 2;
    let pixels_side = modules * SCALE;
    let mut image = egui::ColorImage::new(
        [pixels_side, pixels_side],
        crate::theme::WHITE,
    );
    for y in 0..pixels_side {
        for x in 0..pixels_side {
            let mx = x / SCALE;
            let my = y / SCALE;
            let dark = if mx >= QUIET
                && my >= QUIET
                && mx < QUIET + side
                && my < QUIET + side
            {
                cells.get((my - QUIET) * side + (mx - QUIET)).copied().unwrap_or(false)
            } else {
                false
            };
            image.pixels[y * pixels_side + x] = if dark {
                crate::theme::INK
            } else {
                crate::theme::WHITE
            };
        }
    }
    ctx.load_texture("billflow-upi-qr", image, egui::TextureOptions::NEAREST)
}

/// Helper used by analytics screens to keep a single `Analytics` value in state.
pub fn empty_analytics() -> Analytics {
    Analytics {
        today_sales: 0.0,
        today_transactions: 0,
        month_sales: 0.0,
        month_collections: 0.0,
        year_sales: 0.0,
        outstanding: 0.0,
        pending_invoices: 0,
        low_stock: 0,
        total_customers: 0,
        active_customers: 0,
        growth_percent: 0.0,
        sales_trend: Vec::new(),
        methods: Vec::new(),
        top_products: Vec::new(),
        top_customers: Vec::new(),
        recent_invoices: Vec::new(),
        recent_payments: Vec::new(),
    }
}
