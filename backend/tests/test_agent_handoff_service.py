import pytest

from app.entity.db_models import ChatSession, DatasetVersion, DetectionScene, User
from app.services.agent_handoff_service import AgentHandoffError, agent_handoff_service
from app.services.dataset_service import DatasetLifecycleError


def _records(db_session, *, status="draft"):
    user = User(
        username="handoff-owner",
        email="handoff@example.com",
        hashed_password="test",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    scene = DetectionScene(
        name="handoff-scene",
        display_name="Handoff scene",
        category="retail",
        class_names=["product"],
    )
    db_session.add(scene)
    db_session.flush()
    dataset = DatasetVersion(
        scene_id=scene.id,
        version="draft-v1",
        name="Draft v1",
        status=status,
        is_current=False,
        storage_path="dataset_versions/draft-v1",
        data_yaml_path="data.yaml",
        created_by=user.id,
    )
    session = ChatSession(
        user_id=user.id,
        session_uuid="handoff-session",
        title="handoff",
        status="active",
        message_count=0,
    )
    db_session.add_all([dataset, session])
    db_session.commit()
    return user, dataset, session


def test_create_dataset_add_samples_handoff(db_session):
    user, dataset, session = _records(db_session)

    handoff = agent_handoff_service.create_dataset_add_samples(
        db_session,
        user_id=user.id,
        session_uuid=session.session_uuid,
        dataset_id=dataset.id,
        mode="train_new",
        name="可乐",
        class_name="cola",
        unit_price=3.5,
        barcode="123",
    )
    view = agent_handoff_service.serialize(handoff)

    assert handoff.status == "ready_for_handoff"
    assert handoff.context["mode"] == "train_new"
    assert handoff.context["dataset_id"] == dataset.id
    assert view["page_url"].endswith(handoff.handoff_uuid)


def test_handoff_requires_explicit_new_product_fields(db_session):
    user, dataset, session = _records(db_session)

    with pytest.raises(AgentHandoffError, match="必须明确"):
        agent_handoff_service.create_dataset_add_samples(
            db_session,
            user_id=user.id,
            session_uuid=session.session_uuid,
            dataset_id=dataset.id,
            mode="train_new",
        )


def test_handoff_rejects_non_draft_dataset(db_session):
    user, dataset, session = _records(db_session, status="ready")

    with pytest.raises(DatasetLifecycleError, match="草稿"):
        agent_handoff_service.create_dataset_add_samples(
            db_session,
            user_id=user.id,
            session_uuid=session.session_uuid,
            dataset_id=dataset.id,
            mode="scene",
        )


def test_handoff_status_transitions_are_guarded(db_session):
    user, dataset, session = _records(db_session)
    handoff = agent_handoff_service.create_dataset_add_samples(
        db_session,
        user_id=user.id,
        session_uuid=session.session_uuid,
        dataset_id=dataset.id,
        mode="scene",
    )

    handoff = agent_handoff_service.update(
        db_session,
        handoff_uuid=handoff.handoff_uuid,
        user_id=user.id,
        status="selecting_files",
    )
    handoff = agent_handoff_service.update(
        db_session,
        handoff_uuid=handoff.handoff_uuid,
        user_id=user.id,
        status="annotating",
        context_updates={"total_images": 3},
    )

    assert handoff.context["total_images"] == 3
    with pytest.raises(AgentHandoffError, match="不能从"):
        agent_handoff_service.update(
            db_session,
            handoff_uuid=handoff.handoff_uuid,
            user_id=user.id,
            status="completed",
        )
