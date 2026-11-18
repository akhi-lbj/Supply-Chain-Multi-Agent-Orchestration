# test_control_tower_api.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from src.api.main import app

def test_flow():
    with TestClient(app) as client:
        # 1. Health check
        res = client.get('/health')
        print("1. Health Check:", res.status_code, res.json())
        assert res.status_code == 200

        # 2. Trigger Disruption
        trigger_payload = {
            "sku_code": "SKU_0001",
            "store_id": "STR_DXB_01",
            "delayed_supplier": "SUP_01",
            "delay_days": 5,
            "delayed_units": 500
        }
        res_trigger = client.post("/api/disruptions/trigger", json=trigger_payload)
        print("2. Trigger Status:", res_trigger.status_code)
        assert res_trigger.status_code == 201

        trigger_data = res_trigger.json()
        incident_id = trigger_data["incident_id"]
        approval_id = trigger_data["approval_id"]
        print(f"   Incident ID: {incident_id}")
        print(f"   Approval ID: {approval_id}")
        print(f"   Stockout Window: {trigger_data['disruption_summary']['estimated_stockout_window']}")
        print(f"   Recommended: {trigger_data['recommended_action']}")

        options = trigger_data["ranked_mitigation_options"]
        print(f"   Ranked Mitigation Scenarios ({len(options)} total):")
        for opt in options:
            print(f"     Rank {opt['rank']}: {opt['title']}")
            print(f"       Cost: {opt['total_cost_aed']} AED | Lead Time: {opt['lead_time_hours']} hrs | Reliability: {opt['reliability_score']}")

        # 3. GET /api/disruptions
        res_list = client.get("/api/disruptions")
        print("\n3. GET /api/disruptions:", res_list.status_code)
        assert res_list.status_code == 200
        disruptions = res_list.json()
        print(f"   Active/Resolved Records Found: {len(disruptions)}")
        matched = [d for d in disruptions if d["incident_id"] == incident_id]
        assert len(matched) == 1
        print(f"   Matched Disruption Status: {matched[0]['status']}, Approval: {matched[0]['approval_status']}")

        # 4. POST /api/approvals/{approval_id}/action (APPROVE)
        action_payload = {
            "decision": "APPROVED",
            "notes": "Authorized by Dubai Regional Supply Chain Director for immediate dispatch."
        }
        res_action = client.post(f"/api/approvals/{approval_id}/action", json=action_payload)
        print("\n4. POST /api/approvals/action:", res_action.status_code)
        assert res_action.status_code == 200
        action_data = res_action.json()
        print(f"   Decision: {action_data['decision']} | Status: {action_data['status']}")
        print(f"   Execution Result: {action_data['execution_result']}")

        # 5. Verify update in GET /api/disruptions
        res_list2 = client.get("/api/disruptions")
        updated_item = [d for d in res_list2.json() if d["incident_id"] == incident_id][0]
        print("\n5. Verification after approval:")
        print(f"   Incident Status: {updated_item['status']}")
        print(f"   Approval Status: {updated_item['approval_status']}")
        assert updated_item["status"] == "RESOLVED"
        assert updated_item["approval_status"] == "APPROVED"
        print("\nALL CONTROL TOWER API TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_flow()

