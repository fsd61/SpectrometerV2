"""Global options must work on either side of the subcommand (CLI ergonomics).

Argparse's default arrangement accepts them only before the command, which is
the opposite of how they read — ``--frames`` applies solely to ``stream`` — so
both orderings are supported and pinned here.
"""

import pytest

from app.cli import COMMANDS, build_parser, parse_args


@pytest.mark.parametrize(
    "before, after",
    [
        (["--plot", "run"], ["run", "--plot"]),
        (["-o", "out", "run"], ["run", "-o", "out"]),
        (["--output", "out", "run"], ["run", "--output", "out"]),
        (["-i", "s.csv", "analyze"], ["analyze", "-i", "s.csv"]),
        (["--frames", "60", "stream"], ["stream", "--frames", "60"]),
        (["--force", "init-config"], ["init-config", "--force"]),
        (["--config", "c.ini", "run"], ["run", "--config", "c.ini"]),
        (["-vv", "run"], ["run", "-vv"]),
        (["--set", "a.b=1", "run"], ["run", "--set", "a.b=1"]),
    ],
)
def test_option_placement_is_symmetric(before, after):
    assert vars(parse_args(before)) == vars(parse_args(after))


def test_defaults_when_nothing_supplied():
    args = parse_args(["run"])
    assert args.command == "run"
    assert args.output == "."
    assert args.frames == 30
    assert args.verbose == 0
    assert args.plot is False
    assert args.force is False
    assert args.config is None
    assert args.input is None
    assert args.overrides == []


def test_repeatable_set_merges_across_the_command():
    args = parse_args(["--set", "a.b=1", "run", "--set", "c.d=2"])
    assert args.overrides == ["a.b=1", "c.d=2"]


def test_verbosity_accumulates_across_the_command():
    assert parse_args(["-v", "run", "-v"]).verbose == 2


def test_private_merge_dests_are_removed():
    args = parse_args(["run", "--set", "a.b=1", "-v"])
    assert not [k for k in vars(args) if k.startswith("_after_")]


def test_overrides_default_is_not_shared_between_invocations():
    first = parse_args(["--set", "a.b=1", "run"])
    second = parse_args(["run"])
    assert first.overrides == ["a.b=1"]
    assert second.overrides == []


def test_every_subcommand_accepts_the_common_options():
    for name, _ in COMMANDS:
        args = parse_args([name, "--set", "x.y=1", "-o", "d", "--plot"])
        assert args.command == name
        assert args.overrides == ["x.y=1"]
        assert args.output == "d"
        assert args.plot is True


def test_bare_invocation_has_no_command():
    assert parse_args([]).command is None


def test_unknown_option_still_errors():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "--nope"])


def test_unknown_command_still_errors():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["nope"])
