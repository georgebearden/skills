#!/usr/bin/env python3
"""Heuristic pass: list suspected tautological tests as TSV.

Usage: find_candidates.py <scope-dir>
Output: file:line<TAB>test name<TAB>tags<TAB>note   (summary goes to stderr)

Matches shapes only; every line is a suspect for a human/LLM to judge.
"""
import os
import re
import subprocess
import sys

SKIP_DIRS = {"node_modules", "target", ".git", "dist", "build", "vendor", "__snapshots__", ".venv"}

TS_TEST = re.compile(r"^\s*(?:it|test)(?:\.\w+)*\s*\(\s*([`'\"])(.*?)\1")
RS_TEST = re.compile(r"^\s*#\[(?:tokio::)?test[^\]]*\]")
RS_FN = re.compile(r"^\s*(?:async\s+)?fn\s+(\w+)")
PY_TEST = re.compile(r"^(\s*)(?:async\s+)?def\s+(test\w*)\s*\(")
GO_TEST = re.compile(r"^func\s+(Test\w+)\s*\(")

ASSERT = re.compile(
    r"\bwait\w*\s*\(|\bwaitFor\w*\s*\(|\bexpect\s*\(|\bassert\w*\s*[!(.]|\bassert\b|\bt\.(?:Error|Fatal|Fail)\w*\s*\(|\.should\b|\bverify\s*\(|\bpanic!|\bunreachable!"
)
ALWAYS_TRUE = re.compile(
    r"assert\s*\(?\s*True\s*\)?\s*$|assert!\(\s*true\s*\)|expect\(\s*true\s*\)\.(?:toBe|toBeTruthy)\(\s*true\s*\)"
    r"|expect\((\w+)\)\.(?:toBe|toEqual)\(\1\)|assert_eq!\(\s*(\w+)\s*,\s*\2\s*\)"
)
MOCK_SETUP = re.compile(
    r"mockReturnValue|mockResolvedValue|mockImplementation|\.mockReturnValueOnce|\bwhen\(|\.returns\(|\.with\(|mock_\w+\(|MagicMock|mock\.patch|vi\.fn|jest\.fn|mock\(\)"
)
SNAPSHOT = re.compile(r"toMatchSnapshot|toMatchInlineSnapshot|insta::assert|assert_snapshot|assert_debug_snapshot")
SKIPPED = re.compile(r"^\s*(?:it|test|describe)\.skip\b|^\s*xit\b|#\[ignore")
HELPER_ASSERT = re.compile(r"\b\w*(?:assert|check|verify|expect|validate)\w*\s*\(", re.I)
DISCARD = re.compile(r"^\s*let\s+_\s*=|^\s*let\s+_\w+\s*=")
PRINT_ONLY = re.compile(r"\b(?:println!|eprintln!|dbg!|console\.log|print\()")
ROUNDTRIP = re.compile(r"serde_json::(?:to_string|to_value|to_vec)|JSON\.stringify|json\.dumps")
ROUNDTRIP_BACK = re.compile(r"serde_json::from_|JSON\.parse|json\.loads")
NOT_THROW = re.compile(r"not\.toThrow|\.is_ok\(\)|assert!\(.*\.is_ok\(\)\)|doesNotThrow")


def iter_files(scope):
    for root, dirs, files in os.walk(scope):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            yield os.path.join(root, f)


def is_test_file(path):
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1]
    if ext in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
        return bool(re.search(r"\.(test|spec)\.", name)) or "__tests__" in path
    if ext == ".py":
        return name.startswith("test_") or name.endswith("_test.py")
    if ext == ".go":
        return name.endswith("_test.go")
    if ext == ".rs":
        return True  # inline #[cfg(test)] modules live in ordinary source files
    return False


def brace_block(lines, start):
    """Return end index of the first {...} block at/after start (inclusive)."""
    depth, seen = 0, False
    for i in range(start, len(lines)):
        s = re.sub(r'"(?:\\.|[^"\\])*"', '""', lines[i])
        for ch in s:
            if ch == "{":
                depth += 1
                seen = True
            elif ch == "}":
                depth -= 1
        if seen and depth <= 0:
            return i
    return len(lines) - 1


def indent_block(lines, start, indent):
    end = start
    for i in range(start + 1, len(lines)):
        s = lines[i]
        if s.strip() and len(s) - len(s.lstrip()) <= indent:
            break
        end = i
    return end


def helper_names(lines):
    """Names of same-file functions whose body contains an assertion."""
    names = set()
    decl = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:function\s+(\w+)|(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\(|fn\s+(\w+)|def\s+(\w+))")
    for i, l in enumerate(lines):
        m = decl.match(l)
        if m and not TS_TEST.match(l):
            name = next(g for g in m.groups() if g)
            end = brace_block(lines, i) if "{" in l or (i + 1 < len(lines) and "{" in lines[i + 1]) else i
            if any(ASSERT.search(x) for x in lines[i : end + 1]):
                names.add(name)
    return names


def analyze(body, attrs, helpers=frozenset()):
    text = "\n".join(body)
    code = [l for l in body if not l.strip().startswith(("//", "#", "*"))]
    asserts = [l for l in body if ASSERT.search(l)]
    helper_asserts = [l for l in code[1:] if HELPER_ASSERT.search(l)]
    resolved = [l for l in code[1:] if any(re.search(rf"\b{re.escape(h)}\s*\(", l) for h in helpers)]
    if resolved:
        asserts = asserts + resolved
    tags, notes = [], []
    intentional = bool(re.search(r"should_panic|#\[ignore", attrs))
    skipped = bool(SKIPPED.search(body[0]) or SKIPPED.search(attrs))
    if skipped and len(code) <= 3:
        tags.append("skipped-empty")
    elif not asserts and not intentional:
        if helper_asserts:
            notes.append("assertion may live in a helper; read it")
        else:
            tags.append("no-assertion")
    if ALWAYS_TRUE.search(text):
        tags.append("always-true")
    mocks = sum(1 for l in body if MOCK_SETUP.search(l))
    if mocks >= 3 and mocks / len(body) >= 0.4:
        tags.append("mock-heavy")
        notes.append(f"{mocks}/{len(body)} lines are mock setup")
    if SNAPSHOT.search(text) and len(asserts) <= 1:
        tags.append("self-snapshot")
    if asserts and all(NOT_THROW.search(l) for l in asserts):
        tags.append("only-not-throws")
    discards = sum(1 for l in code if DISCARD.match(l))
    if discards and discards >= max(1, len(code) // 3):
        tags.append("discarded-result")
    if PRINT_ONLY.search(text) and not asserts and not intentional:
        tags.append("print-only")
    if ROUNDTRIP.search(text) and ROUNDTRIP_BACK.search(text) and "JSON.parse(JSON.stringify" not in text and not re.search(r"assert_eq!|toEqual|toStrictEqual|toBe\(", text):
        tags.append("roundtrip-no-compare")
    return tags, notes, len(asserts)


def scan_file(path, out, counts):
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    except OSError:
        return
    ext = os.path.splitext(path)[1]
    helpers = helper_names(lines)
    i = 0
    while i < len(lines):
        line = lines[i]
        name = end = None
        attrs = ""
        if ext in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
            m = TS_TEST.match(line)
            if m:
                name, end = m.group(2), brace_block(lines, i)
        elif ext == ".rs":
            if RS_TEST.match(line):
                j = i + 1
                while j < len(lines) and not RS_FN.match(lines[j]):
                    j += 1
                if j < len(lines):
                    name, end = RS_FN.match(lines[j]).group(1), brace_block(lines, j)
                    attrs = "".join(lines[i:j])  # #[test] plus attrs before fn
        elif ext == ".py":
            m = PY_TEST.match(line)
            if m:
                name, end = m.group(2), indent_block(lines, i, len(m.group(1)))
        elif ext == ".go":
            m = GO_TEST.match(line)
            if m:
                name, end = m.group(1), brace_block(lines, i)
        if name is not None:
            counts["tests"] += 1
            body = lines[i : end + 1]
            k = i
            while k > 0 and lines[k - 1].strip().startswith("#["):
                k -= 1
                attrs += lines[k]
            tags, notes, _ = analyze(body, attrs, helpers)
            if tags or notes:
                counts["flagged"] += 1
                out.append((f"{path}:{i + 1}", name, ",".join(tags), "; ".join(notes)))
            i = max(end, i) + 1
            continue
        i += 1


def main():
    scope = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    out, counts = [], {"tests": 0, "flagged": 0, "files": 0}
    for p in iter_files(scope):
        if is_test_file(p):
            if p.endswith(".rs") and "#[test]" not in open(p, encoding="utf-8", errors="replace").read() \
                    and "::test]" not in open(p, encoding="utf-8", errors="replace").read():
                continue
            counts["files"] += 1
            scan_file(p, out, counts)
    for row in out:
        print("\t".join(row))
    print(f"scanned {counts['tests']} tests in {counts['files']} files; {counts['flagged']} flagged", file=sys.stderr)


if __name__ == "__main__":
    main()
