#!/bin/sh
# Keep the image's Julia depot on the path however this filesystem is run.
#
# Oscar, JSON and the packages sage-julia-bridge's worker project pins live in
# /opt/julia-depot, which the image declares in JULIA_DEPOT_PATH. A container
# runtime applies that declaration to every process; a host that runs the
# unpacked filesystem instead -- PRoot, a bare exec, an entrypoint that rebuilds
# the environment -- does not, and the bridge then stops at julia_bridge.jl:2
# with "Package JSON ... is required but does not seem installed". The depot is
# added to whatever path the caller already has, once.
depot=/opt/julia-depot
case ":${JULIA_DEPOT_PATH-}:" in
  *":$depot:"*) ;;
  *)
    JULIA_DEPOT_PATH="${JULIA_DEPOT_PATH-}"
    case $JULIA_DEPOT_PATH in
      '') JULIA_DEPOT_PATH="$depot:" ;;
      *:) JULIA_DEPOT_PATH="$JULIA_DEPOT_PATH$depot:" ;;
      *) JULIA_DEPOT_PATH="$JULIA_DEPOT_PATH:$depot:" ;;
    esac
    export JULIA_DEPOT_PATH
    ;;
esac
exec /opt/julia/bin/julia "$@"
