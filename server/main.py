from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
from mock_data import inventory_items, orders, demand_forecasts, backlog_items, spending_summary, monthly_spending, category_spending, recent_transactions, purchase_orders

app = FastAPI(title="Factory Inventory Management System")

# Quarter mapping for date filtering
QUARTER_MAP = {
    'Q1-2025': ['2025-01', '2025-02', '2025-03'],
    'Q2-2025': ['2025-04', '2025-05', '2025-06'],
    'Q3-2025': ['2025-07', '2025-08', '2025-09'],
    'Q4-2025': ['2025-10', '2025-11', '2025-12']
}

def filter_by_month(items: list, month: Optional[str]) -> list:
    """Filter items by month/quarter based on order_date field"""
    if not month or month == 'all':
        return items

    if month.startswith('Q'):
        # Handle quarters
        if month in QUARTER_MAP:
            months = QUARTER_MAP[month]
            return [item for item in items if any(m in item.get('order_date', '') for m in months)]
    else:
        # Direct month match
        return [item for item in items if month in item.get('order_date', '')]

    return items

def apply_filters(items: list, warehouse: Optional[str] = None, category: Optional[str] = None,
                 status: Optional[str] = None) -> list:
    """Apply common filters to a list of items"""
    filtered = items

    if warehouse and warehouse != 'all':
        filtered = [item for item in filtered if item.get('warehouse') == warehouse]

    if category and category != 'all':
        filtered = [item for item in filtered if item.get('category', '').lower() == category.lower()]

    if status and status != 'all':
        filtered = [item for item in filtered if item.get('status', '').lower() == status.lower()]

    return filtered

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class InventoryItem(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    warehouse: str
    quantity_on_hand: int
    reorder_point: int
    unit_cost: float
    location: str
    last_updated: str
    lead_time_days: Optional[int] = None

class Order(BaseModel):
    id: str
    order_number: str
    customer: str
    items: List[dict]
    status: str
    order_date: str
    expected_delivery: str
    total_value: float
    actual_delivery: Optional[str] = None
    warehouse: Optional[str] = None
    category: Optional[str] = None

class DemandForecast(BaseModel):
    id: str
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    period: str

class BacklogItem(BaseModel):
    id: str
    order_id: str
    item_sku: str
    item_name: str
    quantity_needed: int
    quantity_available: int
    days_delayed: int
    priority: str
    has_purchase_order: Optional[bool] = False

class PurchaseOrder(BaseModel):
    id: str
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    status: str
    created_date: str
    notes: Optional[str] = None

class CreatePurchaseOrderRequest(BaseModel):
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    notes: Optional[str] = None

# API endpoints
@app.get("/")
def root():
    return {"message": "Factory Inventory Management System API", "version": "1.0.0"}

@app.get("/api/inventory", response_model=List[InventoryItem])
def get_inventory(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get all inventory items with optional filtering"""
    return apply_filters(inventory_items, warehouse, category)

@app.get("/api/inventory/{item_id}", response_model=InventoryItem)
def get_inventory_item(item_id: str):
    """Get a specific inventory item"""
    item = next((item for item in inventory_items if item["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.get("/api/orders", response_model=List[Order])
def get_orders(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get all orders with optional filtering"""
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)
    return filtered_orders

@app.get("/api/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    """Get a specific order"""
    order = next((order for order in orders if order["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/demand", response_model=List[DemandForecast])
def get_demand_forecasts():
    """Get demand forecasts"""
    return demand_forecasts

@app.get("/api/backlog", response_model=List[BacklogItem])
def get_backlog():
    """Get backlog items with purchase order status"""
    # Add has_purchase_order flag to each backlog item
    result = []
    for item in backlog_items:
        item_dict = dict(item)
        # Check if this backlog item has a purchase order
        has_po = any(po["backlog_item_id"] == item["id"] for po in purchase_orders)
        item_dict["has_purchase_order"] = has_po
        result.append(item_dict)
    return result

@app.get("/api/dashboard/summary")
def get_dashboard_summary(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get summary statistics for dashboard with optional filtering"""
    # Filter inventory
    filtered_inventory = apply_filters(inventory_items, warehouse, category)

    # Filter orders
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)

    total_inventory_value = sum(item["quantity_on_hand"] * item["unit_cost"] for item in filtered_inventory)
    low_stock_items = len([item for item in filtered_inventory if item["quantity_on_hand"] <= item["reorder_point"]])
    pending_orders = len([order for order in filtered_orders if order["status"] in ["Processing", "Backordered"]])
    total_backlog_items = len(backlog_items)

    return {
        "total_inventory_value": round(total_inventory_value, 2),
        "low_stock_items": low_stock_items,
        "pending_orders": pending_orders,
        "total_backlog_items": total_backlog_items,
        "total_orders_value": sum(order["total_value"] for order in filtered_orders)
    }

@app.get("/api/spending/summary")
def get_spending_summary():
    """Get spending summary statistics"""
    return spending_summary

@app.get("/api/spending/monthly")
def get_monthly_spending():
    """Get monthly spending breakdown"""
    return monthly_spending

@app.get("/api/spending/categories")
def get_category_spending():
    """Get spending by category"""
    return category_spending

@app.get("/api/spending/transactions")
def get_recent_transactions():
    """Get recent transactions"""
    return recent_transactions

@app.get("/api/reports/quarterly")
def get_quarterly_reports():
    """Get quarterly performance reports"""
    # Calculate quarterly statistics from orders
    quarters = {}

    for order in orders:
        order_date = order.get('order_date', '')
        # Determine quarter
        if '2025-01' in order_date or '2025-02' in order_date or '2025-03' in order_date:
            quarter = 'Q1-2025'
        elif '2025-04' in order_date or '2025-05' in order_date or '2025-06' in order_date:
            quarter = 'Q2-2025'
        elif '2025-07' in order_date or '2025-08' in order_date or '2025-09' in order_date:
            quarter = 'Q3-2025'
        elif '2025-10' in order_date or '2025-11' in order_date or '2025-12' in order_date:
            quarter = 'Q4-2025'
        else:
            continue

        if quarter not in quarters:
            quarters[quarter] = {
                'quarter': quarter,
                'total_orders': 0,
                'total_revenue': 0,
                'delivered_orders': 0,
                'avg_order_value': 0
            }

        quarters[quarter]['total_orders'] += 1
        quarters[quarter]['total_revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            quarters[quarter]['delivered_orders'] += 1

    # Calculate averages and fulfillment rate
    result = []
    for q, data in quarters.items():
        if data['total_orders'] > 0:
            data['avg_order_value'] = round(data['total_revenue'] / data['total_orders'], 2)
            data['fulfillment_rate'] = round((data['delivered_orders'] / data['total_orders']) * 100, 1)
        result.append(data)

    # Sort by quarter
    result.sort(key=lambda x: x['quarter'])
    return result

@app.get("/api/reports/monthly-trends")
def get_monthly_trends():
    """Get month-over-month trends"""
    months = {}

    for order in orders:
        order_date = order.get('order_date', '')
        if not order_date:
            continue

        # Extract month (format: YYYY-MM-DD)
        month = order_date[:7]  # Gets YYYY-MM

        if month not in months:
            months[month] = {
                'month': month,
                'order_count': 0,
                'revenue': 0,
                'delivered_count': 0
            }

        months[month]['order_count'] += 1
        months[month]['revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            months[month]['delivered_count'] += 1

    # Convert to list and sort
    result = list(months.values())
    result.sort(key=lambda x: x['month'])
    return result

# ---------------------------------------------------------------------------
# Restocking
# ---------------------------------------------------------------------------

# Used when an inventory row has no lead_time_days of its own
DEFAULT_LEAD_TIME_DAYS = 14

# Lower rank = restocked first. Unknown trends sort last.
TREND_PRIORITY = {"increasing": 0, "stable": 1, "decreasing": 2}

# Submitted restocking orders (in-memory only, reset on backend restart)
restocking_orders: list = []

class RestockItem(BaseModel):
    sku: str
    quantity: int

class RestockingOrderRequest(BaseModel):
    items: List[RestockItem]
    budget: Optional[float] = None

def _stock_by_sku() -> dict:
    """Aggregate inventory across warehouses, keyed by SKU.

    Stock is summed because a forecast is company-wide demand, not per-warehouse.
    Unit cost is taken from the first row and lead time from the slowest row, so
    an order is never promised faster than its slowest source.
    """
    stock: dict = {}
    for row in inventory_items:
        entry = stock.setdefault(row["sku"], {
            "name": row["name"],
            "unit_cost": row["unit_cost"],
            "quantity_on_hand": 0,
            "lead_time_days": 0,
        })
        entry["quantity_on_hand"] += row["quantity_on_hand"]
        entry["lead_time_days"] = max(entry["lead_time_days"], row.get("lead_time_days") or DEFAULT_LEAD_TIME_DAYS)
    return stock

def _build_recommendations(budget: float) -> dict:
    stock = _stock_by_sku()

    # Candidates: forecast items whose demand exceeds stock on hand
    candidates = []
    for forecast in demand_forecasts:
        inv = stock.get(forecast["item_sku"])
        if not inv or inv["unit_cost"] <= 0:
            continue  # no cost data to budget against
        shortfall = forecast["forecasted_demand"] - inv["quantity_on_hand"]
        if shortfall <= 0:
            continue
        candidates.append({
            "sku": forecast["item_sku"],
            "name": forecast["item_name"],
            "trend": forecast["trend"],
            "forecasted_demand": forecast["forecasted_demand"],
            "quantity_on_hand": inv["quantity_on_hand"],
            "shortfall": shortfall,
            "unit_cost": inv["unit_cost"],
            "lead_time_days": inv["lead_time_days"],
        })

    # Growing demand first, then biggest gap
    candidates.sort(key=lambda c: (TREND_PRIORITY.get(c["trend"], 3), -c["shortfall"]))

    full_restock_cost = round(sum(c["shortfall"] * c["unit_cost"] for c in candidates), 2)

    # Greedy fill: a partial quantity is allowed so the budget is used up, and
    # we keep going after an item we can't afford since cheaper ones may still fit.
    remaining = budget
    recommended = []
    for c in candidates:
        # The epsilon absorbs float drift from repeated subtraction; without it a
        # budget that exactly covers an item can compute one unit short.
        quantity = min(c["shortfall"], int((remaining + 1e-6) // c["unit_cost"]))
        if quantity <= 0:
            continue
        line_total = round(quantity * c["unit_cost"], 2)
        remaining -= line_total
        recommended.append({**c, "recommended_quantity": quantity, "line_total": line_total})

    total_cost = round(sum(r["line_total"] for r in recommended), 2)
    return {
        "budget": budget,
        "total_cost": total_cost,
        "remaining_budget": round(budget - total_cost, 2),
        "full_restock_cost": full_restock_cost,
        "lead_time_days": max((r["lead_time_days"] for r in recommended), default=0),
        "items": recommended,
    }

@app.get("/api/restocking/recommendations")
def get_restocking_recommendations(budget: float = 0):
    """Recommend forecast items to restock within a budget"""
    if budget < 0:
        raise HTTPException(status_code=400, detail="Budget must not be negative")
    return _build_recommendations(budget)

@app.post("/api/restocking-orders", status_code=201)
def create_restocking_order(request: RestockingOrderRequest):
    """Submit a restocking order. Prices and lead times are always taken from
    server-side inventory data, never from the client."""
    if not request.items:
        raise HTTPException(status_code=400, detail="Order must contain at least one item")

    stock = _stock_by_sku()
    lines = []
    for item in request.items:
        inv = stock.get(item.sku)
        if not inv:
            raise HTTPException(status_code=404, detail=f"Unknown SKU: {item.sku}")
        if item.quantity <= 0:
            raise HTTPException(status_code=400, detail=f"Quantity must be positive for {item.sku}")
        lines.append({
            "sku": item.sku,
            "name": inv["name"],
            "quantity": item.quantity,
            "unit_cost": inv["unit_cost"],
            "line_total": round(item.quantity * inv["unit_cost"], 2),
            "lead_time_days": inv["lead_time_days"],
        })

    total_cost = round(sum(l["line_total"] for l in lines), 2)
    if request.budget is not None and total_cost > request.budget:
        raise HTTPException(status_code=400, detail="Order total exceeds budget")

    # The order arrives when its slowest item does
    lead_time_days = max(l["lead_time_days"] for l in lines)
    submitted_at = datetime.now()
    order = {
        "id": f"RO-{len(restocking_orders) + 1:04d}",
        "items": lines,
        "total_cost": total_cost,
        "budget": request.budget,
        "lead_time_days": lead_time_days,
        "submitted_date": submitted_at.isoformat(timespec="seconds"),
        "expected_delivery": (submitted_at + timedelta(days=lead_time_days)).isoformat(timespec="seconds"),
        "status": "Submitted",
    }
    restocking_orders.append(order)
    return order

@app.get("/api/restocking-orders")
def get_restocking_orders():
    """List submitted restocking orders, newest first"""
    return list(reversed(restocking_orders))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
