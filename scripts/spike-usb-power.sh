#!/usr/bin/env bash
#
# Story 1 spike — collect the evidence the acceptance criteria ask for.
#
# Records the Pi model, OS and kernel versions, and the full uhubctl listing, then
# switches the hub off and on again with the light plugged in so the end-to-end behaviour
# is actually observed rather than assumed. Writes a markdown report you can commit.
#
# Usage:  sudo ./scripts/spike-usb-power.sh [-l LOCATION] [-o FILE] [--no-cycle] [--force]
#
set -euo pipefail

LOCATION="${HUB_LOCATION:-2}"
OUTPUT="docs/story-1-spike-results.md"
RUN_CYCLE=1
FORCE=0
OFF_SECONDS=5

usage() {
	sed -n '3,10p' "$0" | sed 's/^# \{0,1\}//'
	exit "${1:-0}"
}

while [ $# -gt 0 ]; do
	case "$1" in
	-l | --location)
		LOCATION="${2:?-l needs a hub location}"
		shift 2
		;;
	-o | --output)
		OUTPUT="${2:?-o needs a path}"
		shift 2
		;;
	--no-cycle)
		RUN_CYCLE=0
		shift
		;;
	--force)
		FORCE=1
		shift
		;;
	-h | --help) usage 0 ;;
	*)
		echo "unknown argument: $1" >&2
		usage 1
		;;
	esac
done

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
die() {
	printf '\033[31m%s\033[0m\n' "$*" >&2
	exit 1
}

ask() { # ask "question" -> 0 if yes
	local reply
	read -r -p "$1 [y/N] " reply </dev/tty
	[ "$reply" = "y" ] || [ "$reply" = "Y" ]
}

# --- preconditions ----------------------------------------------------------------

[ "$(id -u)" -eq 0 ] || die "uhubctl needs raw USB access; re-run with sudo."

command -v uhubctl >/dev/null 2>&1 ||
	die "uhubctl not found. Install it with: sudo apt install -y uhubctl"

# Cutting a ganged hub cuts every downstream port. If the root filesystem lives on one of
# them, that is a hard power-loss on the running system, not a lighting test.
root_source="$(findmnt -no SOURCE / 2>/dev/null || echo '')"
root_is_usb=0
if [ -n "$root_source" ] && command -v udevadm >/dev/null 2>&1; then
	if udevadm info --query=property --name="$root_source" 2>/dev/null |
		grep -qE '^ID_BUS=usb$'; then
		root_is_usb=1
	fi
fi

if [ "$root_is_usb" -eq 1 ]; then
	warn "Root filesystem ($root_source) is on a USB device."
	warn "Switching hub $LOCATION off would cut power to the disk this system is running from."
	if [ "$FORCE" -eq 0 ]; then
		die "Refusing to cycle power. Use backend B (GPIO + relay) on this machine, or pass --force if you are certain hub $LOCATION does not carry the boot device."
	fi
	warn "--force given; continuing anyway."
fi

# --- environment ------------------------------------------------------------------

model="$(tr -d '\0' </proc/device-tree/model 2>/dev/null || echo 'unknown')"
os_version="$(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-unknown}")"
kernel="$(uname -srm)"
uhubctl_version="$(uhubctl --version 2>&1 | head -n1)"

say "Pi model:   $model"
say "OS:         $os_version"
say "Kernel:     $kernel"
say "uhubctl:    $uhubctl_version"

say "Hub listing (look for the capability line on location $LOCATION):"
# uhubctl exits non-zero when it finds no switchable hub — that is itself a result.
hub_listing="$(uhubctl 2>&1 || true)"
printf '%s\n' "$hub_listing"

capability="$(printf '%s\n' "$hub_listing" |
	grep -iE "location $LOCATION\b|^Current status for hub $LOCATION\b" |
	head -n1 || true)"
[ -n "$capability" ] || warn "No line mentioning location $LOCATION found — check the listing above."

case "$capability" in
*ppps*) switching="per-port (ppps) — better than expected; consider -p <port> to shrink the blast radius" ;;
*ganged*) switching="ganged — all downstream ports switch together, as expected" ;;
*) switching="undetermined — read the listing above and fill this in by hand" ;;
esac
say "Switching mode: $switching"

say "Devices currently attached (everything here loses power when the hub is switched off):"
attached="$(lsusb 2>&1 || echo 'lsusb unavailable')"
printf '%s\n' "$attached"

# --- power cycle ------------------------------------------------------------------

cycle_result="not run"
if [ "$RUN_CYCLE" -eq 1 ]; then
	say "About to run: uhubctl -l $LOCATION -a off   (then back on after ${OFF_SECONDS}s)"
	echo "Make sure the light is plugged into hub $LOCATION and is currently lit."
	if ask "Run the power cycle now?"; then
		off_output="$(uhubctl -l "$LOCATION" -a off 2>&1)" || warn "uhubctl off exited non-zero"
		printf '%s\n' "$off_output"
		sleep "$OFF_SECONDS"

		went_dark=no
		ask "Did the light go dark?" && went_dark=yes

		on_output="$(uhubctl -l "$LOCATION" -a on 2>&1)" || warn "uhubctl on exited non-zero"
		printf '%s\n' "$on_output"
		sleep 2

		came_back=no
		ask "Did the light come back on?" && came_back=yes

		if [ "$went_dark" = yes ] && [ "$came_back" = yes ]; then
			cycle_result="verified end-to-end — light went dark on \`off\` and returned on \`on\`"
		else
			cycle_result="FAILED — went dark: $went_dark, came back: $came_back"
		fi
	else
		cycle_result="skipped by operator"
	fi
	say "Power cycle: $cycle_result"
fi

# --- current draw -----------------------------------------------------------------

printf '\nLight current draw in amps (from the label or a USB meter; blank to skip): '
read -r current_draw </dev/tty
current_draw="${current_draw:-not measured}"

draw_note="Budget is ~1.2 A shared across all downstream ports on Pi 3/4."
case "$current_draw" in
not\ measured) draw_note="$draw_note **Still outstanding — this criterion is not met.**" ;;
esac

# --- report -----------------------------------------------------------------------

mkdir -p "$(dirname "$OUTPUT")"
cat >"$OUTPUT" <<EOF
# Story 1 — spike results

Generated by \`scripts/spike-usb-power.sh\` on $(date -Is).
Decision and rationale live in [story-1-usb-power-spike.md](./story-1-usb-power-spike.md).

| | |
|---|---|
| Pi model | $model |
| OS | $os_version |
| Kernel | $kernel |
| uhubctl | $uhubctl_version |
| Hub location switched | \`$LOCATION\` |
| Switching mode | $switching |
| End-to-end power cycle | $cycle_result |
| Light current draw | $current_draw |

$draw_note

## \`uhubctl\` listing

\`\`\`
$hub_listing
\`\`\`

## Devices on the bus at spike time

Everything attached to hub \`$LOCATION\` loses power together whenever the light is
switched. Confirm nothing here matters before accepting the ganged backend.

\`\`\`
$attached
\`\`\`
EOF

say "Wrote $OUTPUT — commit it as the spike artefact."
