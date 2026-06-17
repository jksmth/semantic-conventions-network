# Optional custom advisor — the declarative equivalent of a project-specific
# rule in report.py. This registry is network-only, so any metric whose name is
# not in the `network.*` namespace is a violation (over and above Weaver's
# built-in missing_attribute / type_mismatch / non-registry advisors).
#
# Wire it in with:  weaver registry live-check ... --advice-policies policies
# (flag name may be --advice-policies or --policy depending on weaver version;
#  check `weaver registry live-check --help`).
package live_check_advice

import rego.v1

deny contains make_finding(id, level, context, message) if {
	metric := input.sample.metric
	not startswith(metric.name, "network.")
	id := "non_network_metric"
	level := "violation"
	context := {"metric_name": metric.name}
	message := sprintf("metric '%s' is outside the network.* namespace", [metric.name])
}

make_finding(id, level, context, message) := {
	"id": id,
	"level": level,
	"context": context,
	"message": message,
}
