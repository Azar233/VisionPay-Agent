from app.entity.db_models import (
    AgentPendingOperation,
    ChatSession,
    DatasetClassMapping,
    DatasetVersion,
    DetectionScene,
    OperationLog,
    Product,
    ProductPrice,
    User,
)
from datetime import datetime, timedelta
from app.services.agent_confirmation_service import dataset_workspace_service


def _auth(client, username="confirm_user"):
    client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "123456",
        },
    )
    login = client.post(
        "/api/auth/login", json={"username": username, "password": "123456"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _records(client, db_session):
    headers = _auth(client)
    user = db_session.query(User).filter(User.username == "confirm_user").one()
    scene = DetectionScene(
        name="confirm-scene",
        display_name="确认测试场景",
        category="retail",
        class_names=["cola"],
        created_by=user.id,
    )
    product = Product(product_key="confirm:cola", name="可乐", sku_name="cola")
    db_session.add_all([scene, product])
    db_session.flush()
    dataset = DatasetVersion(
        scene_id=scene.id,
        version="confirm-v1",
        name="确认版本",
        status="pending_train",
        storage_path="dataset_versions/confirm-v1",
        data_yaml_path="data.yaml",
        class_count=1,
        created_by=user.id,
    )
    session = ChatSession(
        user_id=user.id,
        session_uuid="confirmation-session",
        title="确认测试",
        status="active",
        message_count=0,
    )
    db_session.add_all([dataset, session])
    db_session.flush()
    db_session.add(
        DatasetClassMapping(
            dataset_version_id=dataset.id,
            class_index=0,
            product_id=product.id,
            product_key=product.product_key,
            category_id=301,
            class_name="cola",
            display_name="可乐",
        )
    )
    db_session.add(
        ProductPrice(
            product_id=product.id,
            category_id=301,
            sku_name="cola",
            name="可乐",
            unit_price=3.5,
            currency="CNY",
        )
    )
    db_session.commit()
    return headers, user, dataset, product


def _preview(client, headers, dataset_id, product_id, key="preview-price-1"):
    return client.post(
        "/api/agent/operations/preview",
        headers=headers,
        json={
            "session_uuid": "confirmation-session",
            "action": "catalog.update_price",
            "parameters": {
                "dataset_version_id": dataset_id,
                "product_id": product_id,
                "unit_price": 4.2,
                "currency": "CNY",
            },
            "idempotency_key": key,
        },
    )


def test_preview_confirm_one_time_token_idempotency_and_audit(client, db_session):
    headers, user, dataset, product = _records(client, db_session)

    preview = _preview(client, headers, dataset.id, product.id)
    assert preview.status_code == 200, preview.text
    pending = preview.json()
    assert pending["status"] == "pending"
    assert pending["risk_level"] == "R2"
    assert pending["impact"]["changes"]["old_price"] == 3.5
    assert pending["impact"]["changes"]["new_price"] == 4.2
    assert len(pending["confirmation_token"]) >= 20

    invalid = client.post(
        f"/api/agent/operations/{pending['operation_uuid']}/confirm",
        headers=headers,
        json={"confirmation_token": "x" * 32, "idempotency_key": "execute-price-1"},
    )
    assert invalid.status_code == 403
    db_session.expire_all()
    assert db_session.query(ProductPrice).filter_by(product_id=product.id).one().unit_price == 3.5

    confirmed = client.post(
        f"/api/agent/operations/{pending['operation_uuid']}/confirm",
        headers=headers,
        json={
            "confirmation_token": pending["confirmation_token"],
            "idempotency_key": "execute-price-1",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "completed"
    assert confirmed.json()["result"]["unit_price"] == 4.2
    db_session.expire_all()
    assert db_session.query(ProductPrice).filter_by(product_id=product.id).one().unit_price == 4.2

    replay = client.post(
        f"/api/agent/operations/{pending['operation_uuid']}/confirm",
        headers=headers,
        json={
            "confirmation_token": pending["confirmation_token"],
            "idempotency_key": "execute-price-1",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True

    different_key = client.post(
        f"/api/agent/operations/{pending['operation_uuid']}/confirm",
        headers=headers,
        json={
            "confirmation_token": pending["confirmation_token"],
            "idempotency_key": "execute-price-2",
        },
    )
    assert different_key.status_code == 409
    assert db_session.query(OperationLog).filter(
        OperationLog.user_id == user.id,
        OperationLog.target_id == pending["operation_uuid"],
    ).count() >= 4


def test_preview_request_is_idempotent_and_rotates_token(client, db_session):
    headers, _, dataset, product = _records(client, db_session)
    first = _preview(client, headers, dataset.id, product.id).json()
    second_response = _preview(client, headers, dataset.id, product.id)
    assert second_response.status_code == 200
    second = second_response.json()

    assert second["operation_uuid"] == first["operation_uuid"]
    assert second["confirmation_token"] != first["confirmation_token"]
    assert second["replayed"] is True

    stale = client.post(
        f"/api/agent/operations/{first['operation_uuid']}/confirm",
        headers=headers,
        json={"confirmation_token": first["confirmation_token"], "idempotency_key": "stale"},
    )
    assert stale.status_code == 403


def test_pending_operation_can_be_cancelled_and_is_user_scoped(client, db_session):
    headers, _, dataset, product = _records(client, db_session)
    pending = _preview(client, headers, dataset.id, product.id).json()
    other_headers = _auth(client, "confirm_other")

    assert client.get(
        f"/api/agent/operations/{pending['operation_uuid']}", headers=other_headers
    ).status_code == 404
    cancelled = client.post(
        f"/api/agent/operations/{pending['operation_uuid']}/cancel", headers=headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    rejected = client.post(
        f"/api/agent/operations/{pending['operation_uuid']}/confirm",
        headers=headers,
        json={
            "confirmation_token": pending["confirmation_token"],
            "idempotency_key": "cancelled-execute",
        },
    )
    assert rejected.status_code == 409


def test_expired_confirmation_token_is_rejected(client, db_session):
    headers, _, dataset, product = _records(client, db_session)
    pending = _preview(client, headers, dataset.id, product.id).json()
    operation = db_session.query(AgentPendingOperation).filter_by(
        operation_uuid=pending["operation_uuid"]
    ).one()
    operation.token_expires_at = datetime.now() - timedelta(seconds=1)
    db_session.commit()

    response = client.post(
        f"/api/agent/operations/{pending['operation_uuid']}/confirm",
        headers=headers,
        json={
            "confirmation_token": pending["confirmation_token"],
            "idempotency_key": "expired-execute",
        },
    )

    assert response.status_code == 410


def test_frozen_dataset_can_preview_derive_and_current_archive(client, db_session):
    headers, _, dataset, _ = _records(client, db_session)
    dataset.is_current = True
    db_session.commit()

    derive = client.post(
        "/api/agent/operations/preview",
        headers=headers,
        json={
            "session_uuid": "confirmation-session",
            "action": "dataset.derive",
            "parameters": {
                "dataset_id": dataset.id,
                "version": "confirm-v2",
                "name": "确认派生版本",
            },
        },
    )
    archive = client.post(
        "/api/agent/operations/preview",
        headers=headers,
        json={
            "session_uuid": "confirmation-session",
            "action": "dataset.archive",
            "parameters": {"dataset_id": dataset.id},
        },
    )

    assert derive.status_code == 200, derive.text
    assert archive.status_code == 200, archive.text
    assert archive.json()["impact"]["changes"]["status"] == "pending_train → archived"
    assert any("替代当前数据集" in item for item in archive.json()["impact"]["warnings"])


def test_confirmed_dataset_derive_exposes_task_progress(client, db_session, monkeypatch):
    headers, _, dataset, _ = _records(client, db_session)
    progress_updates = []

    def fake_derive(db, *, parent_id, version, name, description, user_id, progress_callback=None):
        del db, parent_id, version, name, description, user_id
        assert progress_callback is not None
        progress_callback(18, "正在复制数据集文件")
        progress_callback(76, "正在重建数据集索引")
        progress_updates.extend([18, 76])
        return dataset

    monkeypatch.setattr(dataset_workspace_service, "derive", fake_derive)
    preview = client.post(
        "/api/agent/operations/preview",
        headers=headers,
        json={
            "session_uuid": "confirmation-session",
            "action": "dataset.derive",
            "parameters": {
                "dataset_id": dataset.id,
                "version": "confirm-progress-v2",
                "name": "确认派生进度版本",
            },
        },
    ).json()

    confirmed = client.post(
        f"/api/agent/operations/{preview['operation_uuid']}/confirm",
        headers=headers,
        json={
            "confirmation_token": preview["confirmation_token"],
            "idempotency_key": "execute-derive-progress",
        },
    )

    assert confirmed.status_code == 200, confirmed.text
    assert progress_updates == [18, 76]
    assert confirmed.json()["task_progress"]["status"] == "completed"
    assert confirmed.json()["task_progress"]["progress"] == 100
    assert [item["progress"] for item in confirmed.json()["task_progress"]["history"]] == [
        0,
        18,
        76,
        100,
    ]
    current = client.get(
        f"/api/agent/operations/{preview['operation_uuid']}", headers=headers
    ).json()
    assert current["task_progress"]["progress"] == 100


def test_new_preview_supersedes_pending_operation_for_same_product(client, db_session):
    headers, user, dataset, product = _records(client, db_session)

    first = client.post(
        "/api/agent/operations/preview",
        headers=headers,
        json={
            "session_uuid": "confirmation-session",
            "action": "catalog.update_price",
            "parameters": {
                "dataset_version_id": dataset.id,
                "product_id": product.id,
                "unit_price": 4.2,
                "currency": "CNY",
            },
        },
    )
    assert first.status_code == 200, first.text
    first_uuid = first.json()["operation_uuid"]

    # 同一商品生成第二个不同价格的预览：旧的待确认必须被取代，避免叠加执行。
    second = client.post(
        "/api/agent/operations/preview",
        headers=headers,
        json={
            "session_uuid": "confirmation-session",
            "action": "catalog.update_price",
            "parameters": {
                "dataset_version_id": dataset.id,
                "product_id": product.id,
                "unit_price": 5.0,
                "currency": "CNY",
            },
        },
    )
    assert second.status_code == 200, second.text
    second_uuid = second.json()["operation_uuid"]
    assert second_uuid != first_uuid

    operations = db_session.query(AgentPendingOperation).filter(
        AgentPendingOperation.operation_uuid.in_([first_uuid, second_uuid])
    ).all()
    by_uuid = {operation.operation_uuid: operation.status for operation in operations}
    assert by_uuid[first_uuid] == "cancelled"
    assert by_uuid[second_uuid] == "pending"

    # 不同商品的待确认互不影响。
    other = Product(product_key="confirm:other", name="雪碧", sku_name="sprite")
    db_session.add(other)
    db_session.flush()
    db_session.add(
        DatasetClassMapping(
            dataset_version_id=dataset.id,
            class_index=1,
            product_id=other.id,
            product_key=other.product_key,
            category_id=302,
            class_name="sprite",
            display_name="雪碧",
        )
    )
    db_session.commit()
    third = client.post(
        "/api/agent/operations/preview",
        headers=headers,
        json={
            "session_uuid": "confirmation-session",
            "action": "catalog.update_price",
            "parameters": {
                "dataset_version_id": dataset.id,
                "product_id": other.id,
                "unit_price": 6.0,
                "currency": "CNY",
            },
        },
    )
    assert third.status_code == 200, third.text
    db_session.expire_all()
    still_pending = db_session.query(AgentPendingOperation).filter(
        AgentPendingOperation.operation_uuid == second_uuid
    ).one()
    assert still_pending.status == "pending"
