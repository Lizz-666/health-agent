import 'package:flutter_test/flutter_test.dart';
import 'package:posture_app/models/agent.dart';

Map<String, dynamic> _disclosure() => {
  'disclosure_version': 'agent-disclosure-v1',
  'provider_id': 'dashscope',
  'provider_name_zh': '通义千问（DashScope）',
  'purpose_code': 'wellness_agent_assistance',
  'processing_boundary_code': 'cloud_model_processing',
  'data_scope_codes': ['structured_health_context', 'ephemeral_user_message'],
  'application_retention_code': 'no_chat_transcript_persistence',
  'withdrawal_available': true,
  'agent_data_deletion_available': true,
};

Map<String, dynamic> _capabilities() => {
  'runtime_enabled': true,
  'provider_configured': true,
  'provider_id': 'dashscope',
  'model_id': 'qwen-plus',
  'disclosure_version': 'agent-disclosure-v1',
  'consent_active': true,
  'available': true,
  'result_code': 'agent_available',
  'message': 'Agent 已满足当前运行与隐私条件。',
  'disclosure': _disclosure(),
};

Map<String, dynamic> _proposal({
  String action = 'create_weight_record',
  Map<String, dynamic>? diff,
}) => {
  'proposal_id': '10000000-0000-4000-8000-000000000001',
  'action': action,
  'diff':
      diff ??
      {
        'action': 'create_weight_record',
        'summary_code': 'weight_record_change',
        'recorded_at': '2026-07-30T08:00:00Z',
        'weight_kg': 70.5,
      },
  'expires_at': '2099-07-30T08:15:00Z',
};

Map<String, dynamic> _turn({
  String status = 'answer',
  String code = 'agent_answer_ready',
  Map<String, dynamic>? proposal,
  List<Map<String, dynamic>>? displays,
  bool replayed = false,
}) => {
  'run_id': '20000000-0000-4000-8000-000000000001',
  'status': status,
  'message': '已根据当前可访问的信息整理结果。',
  'result_code': code,
  'display_data': displays ?? <Map<String, dynamic>>[],
  'proposal': proposal,
  'replayed': replayed,
};

void main() {
  group('Agent route context', () {
    test('round trips only entry type and entity id', () {
      final context = AgentRouteContext.fromQuery({
        'entry_type': 'training_exercise',
        'entity_id': 'exercise-1',
      });

      expect(context.entryType, AgentEntryType.trainingExercise);
      expect(context.entityId, 'exercise-1');
      expect(context.toQuery(), {
        'entry_type': 'training_exercise',
        'entity_id': 'exercise-1',
      });
    });

    test('unknown route fields fail closed', () {
      expect(
        () => AgentRouteContext.fromQuery({
          'entry_type': 'general',
          'health_payload': 'not-allowed',
        }),
        throwsFormatException,
      );
      expect(
        () => AgentRouteContext.fromQuery({'entry_type': 'medical'}),
        throwsFormatException,
      );
    });
  });

  group('capabilities and disclosure', () {
    test('valid current capability parses', () {
      final result = AgentCapabilities.fromJson(_capabilities());
      expect(result.available, isTrue);
      expect(result.disclosure?.providerId, 'dashscope');
      expect(result.disclosure?.dataScopeCodes, hasLength(2));
    });

    test('unknown keys and result codes fail closed', () {
      final withExtra = _capabilities()..['raw_prompt'] = 'forbidden';
      expect(
        () => AgentCapabilities.fromJson(withExtra),
        throwsFormatException,
      );

      final unknownCode = _capabilities()..['result_code'] = 'looks_successful';
      expect(
        () => AgentCapabilities.fromJson(unknownCode),
        throwsFormatException,
      );
    });

    test('inconsistent availability and disclosure fail closed', () {
      final withoutConsent = _capabilities()..['consent_active'] = false;
      expect(
        () => AgentCapabilities.fromJson(withoutConsent),
        throwsFormatException,
      );

      final mismatchedDisclosure = _capabilities();
      mismatchedDisclosure['disclosure'] = {
        ..._disclosure(),
        'disclosure_version': 'unseen-disclosure-v2',
      };
      expect(
        () => AgentCapabilities.fromJson(mismatchedDisclosure),
        throwsFormatException,
      );
    });
  });

  group('turn response', () {
    test('known read display parses and preserves structured values', () {
      final result = AgentTurnResponse.fromJson(
        _turn(
          displays: [
            {
              'tool_name': 'get_today_training',
              'data': {
                'state': 'session',
                'exercise_ids': ['exercise-1'],
              },
            },
          ],
        ),
      );

      expect(result.status, AgentTurnStatus.answer);
      expect(result.displayData.single.data['state'], 'session');
    });

    test('unknown tool and malformed pending state fail closed', () {
      expect(
        () => AgentTurnResponse.fromJson(
          _turn(
            displays: [
              {'tool_name': 'run_sql', 'data': <String, dynamic>{}},
            ],
          ),
        ),
        throwsFormatException,
      );
      expect(
        () => AgentTurnResponse.fromJson(
          _turn(
            status: 'proposal_pending',
            code: 'agent_action_confirmation_required',
          ),
        ),
        throwsFormatException,
      );
    });

    test('proposal is accepted only for pending or replayed states', () {
      final pending = AgentTurnResponse.fromJson(
        _turn(
          status: 'proposal_pending',
          code: 'agent_action_confirmation_required',
          proposal: _proposal(),
        ),
      );
      expect(pending.proposal?.diff, isA<WeightActionDiff>());

      expect(
        () => AgentTurnResponse.fromJson(
          _turn(status: 'answer', proposal: _proposal()),
        ),
        throwsFormatException,
      );
    });

    test('replay flag must match the replay status', () {
      expect(
        () => AgentTurnResponse.fromJson(
          _turn(status: 'replayed', replayed: false),
        ),
        throwsFormatException,
      );
      expect(
        () => AgentTurnResponse.fromJson(_turn(replayed: true)),
        throwsFormatException,
      );
    });
  });

  group('typed proposal diffs', () {
    test('parses all five allowlisted actions', () {
      final fixtures = <Map<String, dynamic>>[
        _proposal(
          action: 'upsert_today_checkin',
          diff: {
            'action': 'upsert_today_checkin',
            'summary_code': 'checkin_change',
            'local_date': '2026-07-30',
            'abnormal_pain': false,
          },
        ),
        _proposal(),
        _proposal(
          action: 'generate_training_plan_draft',
          diff: {
            'action': 'generate_training_plan_draft',
            'summary_code': 'plan_draft_change',
            'fitness_goal': 'basic_strength',
            'weekly_frequency': 3,
            'session_duration_minutes': 30,
            'requires_plan_review': true,
          },
        ),
        _proposal(
          action: 'substitute_today_exercise',
          diff: {
            'action': 'substitute_today_exercise',
            'summary_code': 'exercise_substitution',
            'session_id': 'session-1',
            'original_exercise_id': 'exercise-1',
            'replacement_exercise_id': 'exercise-2',
          },
        ),
        _proposal(
          action: 'record_training_feedback',
          diff: {
            'action': 'record_training_feedback',
            'summary_code': 'training_feedback',
            'outcome_state': 'partial',
          },
        ),
      ];

      final parsed = fixtures.map(AgentProposal.fromJson).toList();
      expect(parsed[0].diff, isA<CheckinActionDiff>());
      expect(parsed[1].diff, isA<WeightActionDiff>());
      expect(parsed[2].diff, isA<PlanDraftActionDiff>());
      expect(parsed[3].diff, isA<SubstitutionActionDiff>());
      expect(parsed[4].diff, isA<FeedbackActionDiff>());
      expect((parsed[4].diff as FeedbackActionDiff).sessionId, isNull);
    });

    test('action/diff mismatch and prohibited discomfort fail closed', () {
      expect(
        () => AgentProposal.fromJson(
          _proposal(
            action: 'create_weight_record',
            diff: {
              'action': 'record_training_feedback',
              'summary_code': 'wrong',
              'session_id': 'session-1',
              'outcome_state': 'completed',
            },
          ),
        ),
        throwsFormatException,
      );
      expect(
        () => AgentProposal.fromJson(
          _proposal(
            action: 'record_training_feedback',
            diff: {
              'action': 'record_training_feedback',
              'summary_code': 'feedback',
              'session_id': 'session-1',
              'outcome_state': 'discomfort',
            },
          ),
        ),
        throwsFormatException,
      );
    });
  });

  group('terminal response contracts', () {
    test('executed response is not inferred from arbitrary status', () {
      final executed = AgentActionResponse.fromJson({
        'proposal_id': '10000000-0000-4000-8000-000000000001',
        'status': 'executed',
        'result_code': 'agent_action_executed',
        'result_ref': 'record-1',
        'message': '操作已按确认内容执行。',
      });
      expect(executed.executed, isTrue);

      expect(
        () => AgentActionResponse.fromJson({
          'proposal_id': '10000000-0000-4000-8000-000000000001',
          'status': 'cancelled',
          'result_code': 'agent_action_executed',
          'result_ref': null,
          'message': 'bad',
        }),
        throwsFormatException,
      );
    });

    test('blocked and non-success replays remain non-executed', () {
      final blocked = AgentActionResponse.fromJson({
        'proposal_id': '10000000-0000-4000-8000-000000000001',
        'status': 'blocked',
        'result_code': 'agent_disabled',
        'result_ref': null,
        'message': 'Agent 当前未启用，其他功能仍可正常使用。',
      });
      final replayedRejection = AgentActionResponse.fromJson({
        'proposal_id': '10000000-0000-4000-8000-000000000001',
        'status': 'replayed',
        'result_code': 'agent_context_stale',
        'result_ref': null,
        'message': '相关信息已变化，请重新发起操作。',
      });

      expect(blocked.executed, isFalse);
      expect(replayedRejection.executed, isFalse);
    });

    test('deletion counters must be complete and non-negative', () {
      final result = AgentDataDeletionResult.fromJson({
        'deleted': true,
        'consents_deleted': 1,
        'runs_deleted': 2,
        'tool_events_deleted': 3,
        'proposals_deleted': 4,
        'idempotency_deleted': 5,
      });
      expect(result.proposalsDeleted, 4);

      expect(
        () => AgentDataDeletionResult.fromJson({
          'deleted': true,
          'consents_deleted': -1,
          'runs_deleted': 0,
          'tool_events_deleted': 0,
          'proposals_deleted': 0,
          'idempotency_deleted': 0,
        }),
        throwsFormatException,
      );
    });
  });
}
