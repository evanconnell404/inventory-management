"""
Tests for restocking API endpoints.
"""
from datetime import datetime, timedelta


class TestRestockingRecommendations:
    """Test suite for budget-based restocking recommendations."""

    def test_zero_budget_returns_no_items_but_full_cost(self, client):
        """A zero budget buys nothing but still reports the cost to cover every shortfall."""
        response = client.get("/api/restocking/recommendations?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert data["items"] == []
        assert data["total_cost"] == 0
        assert data["lead_time_days"] == 0
        assert data["full_restock_cost"] > 0

    def test_recommendation_structure(self, client):
        """Test that recommended items carry every field the UI needs."""
        data = client.get("/api/restocking/recommendations?budget=1000000").json()
        assert len(data["items"]) > 0

        for item in data["items"]:
            for field in ("sku", "name", "trend", "forecasted_demand", "quantity_on_hand",
                          "shortfall", "unit_cost", "lead_time_days", "recommended_quantity",
                          "line_total"):
                assert field in item
            assert item["recommended_quantity"] > 0
            assert item["shortfall"] > 0

    def test_total_cost_never_exceeds_budget(self, client):
        """Test that spend stays within the budget for a range of budgets."""
        for budget in (50, 500, 2500, 7500, 15000):
            data = client.get(f"/api/restocking/recommendations?budget={budget}").json()
            assert data["total_cost"] <= budget
            assert abs(data["remaining_budget"] - (budget - data["total_cost"])) < 0.01

    def test_line_totals_sum_to_total_cost(self, client):
        """Test that line totals add up to the reported total."""
        data = client.get("/api/restocking/recommendations?budget=5000").json()
        calculated = sum(i["line_total"] for i in data["items"])
        assert abs(data["total_cost"] - calculated) < 0.01

        for item in data["items"]:
            assert abs(item["line_total"] - item["recommended_quantity"] * item["unit_cost"]) < 0.01

    def test_large_budget_covers_every_shortfall(self, client):
        """Test that a budget of full_restock_cost fully covers each shortfall."""
        full_cost = client.get("/api/restocking/recommendations?budget=0").json()["full_restock_cost"]
        data = client.get(f"/api/restocking/recommendations?budget={full_cost}").json()

        assert abs(data["total_cost"] - full_cost) < 0.01
        for item in data["items"]:
            assert item["recommended_quantity"] == item["shortfall"]

    def test_increasing_trends_prioritized(self, client):
        """Test that growing-demand items come before stable and decreasing ones."""
        data = client.get("/api/restocking/recommendations?budget=1000000").json()
        rank = {"increasing": 0, "stable": 1, "decreasing": 2}
        ranks = [rank.get(i["trend"], 3) for i in data["items"]]
        assert ranks == sorted(ranks)

    def test_only_items_with_shortfall_recommended(self, client):
        """Test that items whose stock already meets forecast are skipped."""
        data = client.get("/api/restocking/recommendations?budget=1000000").json()
        for item in data["items"]:
            assert item["forecasted_demand"] > item["quantity_on_hand"]

    def test_order_lead_time_is_slowest_item(self, client):
        """Test that the order lead time equals the longest item lead time."""
        data = client.get("/api/restocking/recommendations?budget=1000000").json()
        assert data["lead_time_days"] == max(i["lead_time_days"] for i in data["items"])

    def test_negative_budget_rejected(self, client):
        """Test that a negative budget returns 400."""
        response = client.get("/api/restocking/recommendations?budget=-5")
        assert response.status_code == 400
        assert "detail" in response.json()


class TestRestockingOrders:
    """Test suite for submitting and listing restocking orders."""

    def _recommended_payload(self, client, budget=5000):
        data = client.get(f"/api/restocking/recommendations?budget={budget}").json()
        items = [{"sku": i["sku"], "quantity": i["recommended_quantity"]} for i in data["items"]]
        return data, {"items": items, "budget": budget}

    def test_create_order(self, client):
        """Test submitting the recommended items creates an order."""
        recommendation, payload = self._recommended_payload(client)
        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        assert order["id"].startswith("RO-")
        assert order["status"] == "Submitted"
        assert abs(order["total_cost"] - recommendation["total_cost"]) < 0.01
        assert order["lead_time_days"] == recommendation["lead_time_days"]
        assert len(order["items"]) == len(payload["items"])

    def test_expected_delivery_matches_lead_time(self, client):
        """Test that expected delivery is submission date plus the lead time."""
        _, payload = self._recommended_payload(client)
        order = client.post("/api/restocking-orders", json=payload).json()

        submitted = datetime.fromisoformat(order["submitted_date"])
        expected = datetime.fromisoformat(order["expected_delivery"])
        assert expected - submitted == timedelta(days=order["lead_time_days"])

    def test_order_appears_in_list_newest_first(self, client):
        """Test that a submitted order is listed, with the newest first."""
        _, payload = self._recommended_payload(client)
        first = client.post("/api/restocking-orders", json=payload).json()
        second = client.post("/api/restocking-orders", json=payload).json()

        listed = client.get("/api/restocking-orders").json()
        ids = [o["id"] for o in listed]
        assert second["id"] in ids and first["id"] in ids
        assert ids.index(second["id"]) < ids.index(first["id"])

    def test_prices_come_from_server_not_client(self, client):
        """Test that client-supplied prices are ignored."""
        recommendation, _ = self._recommended_payload(client)
        item = recommendation["items"][0]
        payload = {"items": [{"sku": item["sku"], "quantity": 1, "unit_cost": 0.01}]}

        order = client.post("/api/restocking-orders", json=payload).json()
        assert order["items"][0]["unit_cost"] == item["unit_cost"]

    def test_empty_order_rejected(self, client):
        """Test that an order with no items returns 400."""
        response = client.post("/api/restocking-orders", json={"items": []})
        assert response.status_code == 400
        assert "detail" in response.json()

    def test_unknown_sku_returns_404(self, client):
        """Test that an unknown SKU returns 404."""
        response = client.post("/api/restocking-orders", json={"items": [{"sku": "NOPE-000", "quantity": 1}]})
        assert response.status_code == 404
        assert "unknown sku" in response.json()["detail"].lower()

    def test_non_positive_quantity_rejected(self, client):
        """Test that zero or negative quantities return 400."""
        sku = client.get("/api/restocking/recommendations?budget=1000000").json()["items"][0]["sku"]
        for quantity in (0, -3):
            response = client.post("/api/restocking-orders", json={"items": [{"sku": sku, "quantity": quantity}]})
            assert response.status_code == 400

    def test_order_over_budget_rejected(self, client):
        """Test that an order costing more than its budget returns 400."""
        _, payload = self._recommended_payload(client)
        payload["budget"] = 1
        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()

    def test_missing_items_field_is_validation_error(self, client):
        """Test that a malformed body returns 422."""
        response = client.post("/api/restocking-orders", json={})
        assert response.status_code == 422
