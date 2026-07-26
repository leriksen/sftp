#!/usr/bin/env python3
"""Merge two or more pytest-generated JUnit XML files into one <testsuites>
document. Handles both root shapes pytest has used across versions (a bare
<testsuite> root, or <testsuites> wrapping one <testsuite>).

Usage: merge_junit.py IN.xml [IN2.xml ...] OUT.xml
"""
import sys
import xml.etree.ElementTree as ET


def merge(inputs, output):
    root = ET.Element("testsuites")
    for path in inputs:
        src_root = ET.parse(path).getroot()
        suites = src_root if src_root.tag == "testsuites" else [src_root]
        for suite in suites:
            root.append(suite)
    ET.ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    *inputs, output = sys.argv[1:]
    merge(inputs, output)
