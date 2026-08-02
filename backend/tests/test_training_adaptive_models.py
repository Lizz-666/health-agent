from app.training.models import (
    PostureRecheckDismissal,
    TrainingDayAdjustment,
    TrainingDayAdjustmentItem,
    TrainingWeeklyReview,
)


def _constraint_names(model):
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if constraint.name is not None
    }


def test_adjustment_model_is_append_only_typed_and_owner_scoped():
    columns = TrainingDayAdjustment.__table__.columns
    assert {
        "adjustment_id",
        "user_id",
        "plan_version_id",
        "source_session_id",
        "source_local_date",
        "target_local_date",
        "adjustment_kind",
        "trigger_code",
        "reason_codes",
        "source_context_fingerprint",
        "decision_fingerprint",
        "adaptive_policy_version",
        "training_policy_version",
        "catalog_version",
        "source_manifest_version",
        "surface",
        "target_minutes",
        "created_at",
    }.issubset(columns.keys())
    assert "raw_note" not in columns
    assert "status" not in columns
    assert "uq_training_day_adjustments_decision" in _constraint_names(
        TrainingDayAdjustment
    )
    assert "ck_training_day_adjustments_kind" in _constraint_names(
        TrainingDayAdjustment
    )
    assert "ck_training_day_adjustments_surface" in _constraint_names(
        TrainingDayAdjustment
    )
    kind_constraint = next(
        constraint
        for constraint in TrainingDayAdjustment.__table__.constraints
        if constraint.name == "ck_training_day_adjustments_kind"
    )
    assert "'unchanged'" in str(kind_constraint.sqltext)


def test_adjustment_items_are_typed_and_ordered():
    columns = TrainingDayAdjustmentItem.__table__.columns
    assert {
        "adjustment_item_id",
        "adjustment_id",
        "source_prescription_id",
        "item_action",
        "effective_exercise_id",
        "sets",
        "reps",
        "duration_seconds",
        "rest_seconds",
        "display_order",
    }.issubset(columns.keys())
    assert "uq_training_day_adjustment_items_source" in _constraint_names(
        TrainingDayAdjustmentItem
    )
    assert "ck_training_day_adjustment_items_action" in _constraint_names(
        TrainingDayAdjustmentItem
    )


def test_review_and_dismissal_models_have_replay_keys_without_prose():
    review_columns = TrainingWeeklyReview.__table__.columns
    assert "input_fingerprint" in review_columns
    assert "facts" in review_columns
    assert "proposal_codes" in review_columns
    assert "raw_notes" not in review_columns
    assert "uq_training_weekly_reviews_fingerprint" in _constraint_names(
        TrainingWeeklyReview
    )
    assert "ck_training_weekly_reviews_week" in _constraint_names(
        TrainingWeeklyReview
    )

    dismissal_columns = PostureRecheckDismissal.__table__.columns
    assert "plan_version_id" in dismissal_columns
    assert "dismissed_at" in dismissal_columns
    assert "uq_posture_recheck_dismissals_cycle" in _constraint_names(
        PostureRecheckDismissal
    )
