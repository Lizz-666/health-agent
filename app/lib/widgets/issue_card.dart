// app/lib/widgets/issue_card.dart
import 'package:flutter/material.dart';
import '../core/constants.dart';
import '../models/issue.dart';

class IssueCard extends StatelessWidget {
  final IssueSummary issue;
  final String? result;
  final VoidCallback onTap;

  const IssueCard({
    super.key,
    required this.issue,
    this.result,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          issue.nameCn,
                          style: const TextStyle(
                            fontSize: 17,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(width: 8),
                        if (result != null) _resultBadge(result!),
                      ],
                    ),
                    if (issue.aliases.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 6,
                        children: issue.aliases
                            .map(
                              (a) => Chip(
                                label: Text(
                                  a,
                                  style: const TextStyle(fontSize: 11),
                                ),
                                padding: EdgeInsets.zero,
                                materialTapTargetSize:
                                    MaterialTapTargetSize.shrinkWrap,
                                visualDensity: VisualDensity.compact,
                              ),
                            )
                            .toList(),
                      ),
                    ],
                    const SizedBox(height: 8),
                    Text(
                      issue.definition,
                      style: const TextStyle(
                        color: Color(0xFF8892B0),
                        fontSize: 13,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: Color(0xFF8892B0)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _resultBadge(String r) {
    final colors = {
      'normal': AppConstants.normalColor,
      'moderate': AppConstants.moderateColor,
      'severe': AppConstants.severeColor,
    };
    final labels = {'normal': '正常', 'moderate': '需关注', 'severe': '严重'};
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: Color(
          colors[r] ?? AppConstants.primaryColor,
        ).withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        labels[r] ?? r,
        style: TextStyle(
          color: Color(colors[r] ?? AppConstants.primaryColor),
          fontSize: 11,
        ),
      ),
    );
  }
}
