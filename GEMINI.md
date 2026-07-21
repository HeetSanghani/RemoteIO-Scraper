
## Code Review Graph — MANDATORY
Before making ANY code change:
1. Call get_minimal_context_tool to load the graph
2. Call get_impact_radius_tool on files you plan to change
3. Review blast radius before editing
4. After changes, call detect_changes_tool to verify impact
Never modify code without checking the graph first.

