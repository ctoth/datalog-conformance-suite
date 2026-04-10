from __future__ import annotations

THEORIES = {
    "baseline_birds": """
bird(X) <- chicken(X).
bird(X) <- penguin(X).
~flies(X) <- penguin(X).
chicken(tina).
penguin(tweety).
scared(tina).
flies(X) -< bird(X).
flies(X) -< chicken(X), scared(X).
~flies(X) -< chicken(X).
nests_in_trees(X) -< flies(X).
""",
    "positive_chicken": """
bird(X) <- chicken(X).
chicken(henrietta).
scared(henrietta).
flies(X) -< bird(X).
flies(X) -< chicken(X), scared(X).
nests_in_trees(X) -< flies(X).
""",
}


def main() -> None:
    from depysible.domain.definitions import Program, RuleType
    from depysible.domain.interpretation import Interpreter

    for name, theory in THEORIES.items():
        print(f"== {name} ==")
        program = Program.parse(theory)
        interpreter = Interpreter(program)

        print("STRICT")
        for literal in sorted(interpreter.get_literals(RuleType.STRICT), key=repr):
            answer, _ = interpreter.query(literal, RuleType.STRICT)
            print(repr(literal), answer.name)

        print("DEFEASIBLE")
        for literal in sorted(interpreter.get_literals(RuleType.DEFEASIBLE), key=repr):
            answer, _ = interpreter.query(literal, RuleType.DEFEASIBLE)
            print(repr(literal), answer.name)


if __name__ == "__main__":
    main()
