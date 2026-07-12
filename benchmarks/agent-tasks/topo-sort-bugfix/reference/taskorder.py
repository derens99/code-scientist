"""Topological ordering of named tasks with dependencies.

topological_order(dependencies) takes a dict mapping each task name to a
list of prerequisite task names that must appear earlier in the result.
Every task name mentioned anywhere (as a key or in a dependency list) must
appear exactly once in the output. When multiple tasks are simultaneously
ready to run (no unprocessed prerequisites), they must appear in the
output in alphabetical order for determinism. If the dependencies contain
a cycle, raise ValueError.
"""


def topological_order(dependencies):
    all_tasks = set(dependencies.keys())
    for deps in dependencies.values():
        all_tasks.update(deps)

    remaining = {t: set(dependencies.get(t, [])) for t in all_tasks}
    result = []
    while remaining:
        ready = [t for t, deps in remaining.items() if not deps]
        if not ready:
            raise ValueError("cycle detected in dependencies")
        ready.sort()
        for t in ready:
            del remaining[t]
            result.append(t)
        for deps in remaining.values():
            deps.difference_update(ready)
    return result
