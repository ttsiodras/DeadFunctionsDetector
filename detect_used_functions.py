#!/usr/bin/env python2
"""
A utility that parses pre-processed (standalone) C files using Clang,
and then detects the functions that are used - anywhere.
"""
from __future__ import print_function

import os
import sys
import pickle
from collections import defaultdict

# For mypy static type checks.
from typing import Set, Optional, List, Tuple, Any, Dict  # NOQA

from clang.cindex import (
    CursorKind, Index, TranslationUnit, TranslationUnitLoadError)

SET_OF_ALL_FUNCTIONS = set()   # type: Set[str]

CACHE_FUNCTION_NAMES = '.function_names'
CACHE_CALL_GRAPH = '.call_graph'


def find_funcs_and_calls(t_unit, set_of_function_names, cursor_work):
    # type: (Any, Set[str], Any) -> Dict[str, List[str]]
    """
    Collects all the calls made by functions inside a translation unit, as
    well as update the passed-in set_of_function_names with the set of
    functions defined in this translation unit.
    """
    filename = t_unit.cursor.spelling
    print("[-] Identifying calls made inside functions of", filename)
    calls_made_by = defaultdict(list)  # type: Dict[str, List[str]]
    current_function = None            # type: Optional[str]
    for node in t_unit.cursor.walk_preorder():
        cursor_work(node)
        if node.location.file is None:
            pass
        elif node.location.file.name != filename:
            pass
        elif node.kind == CursorKind.CALL_EXPR:
            # We are calling someone
            callee = node.spelling
            if current_function is not None and \
                    callee not in calls_made_by[current_function]:
                # Add him in the list.
                calls_made_by[current_function].append(callee)
        elif node.kind == CursorKind.FUNCTION_DECL:
            # Oh good, new function definition starts
            current_function = node.mangled_name
            set_of_function_names.add(current_function)  # type: ignore
    return calls_made_by


def parse_calls(unused_idx, t_units, cursor_work):
    # type: (Any, List[Any], Any) -> Tuple[ Dict[str,List[str]], Set[str] ]
    """
    Gather all the calls made by all translation units.
    Also, collect all defined functions' names.
    """
    set_of_function_names = set()      # type: Set[str]
    calls_made_by_all_funcs = defaultdict(list)  # type: Dict[str,List[str]]
    for t_unit in t_units:
        # Gather all the calls made by functions in this C file
        calls_made_by_this_tu = find_funcs_and_calls(
            t_unit, set_of_function_names, cursor_work)
        # For each one of the functions in this C file,
        for func, calls in calls_made_by_this_tu.items():
            # enumerate over all the calls it made
            for funcname in calls:
                # ...and gather them in the global dictionary.
                calls_made_by_all_funcs[func].append(funcname)
    return calls_made_by_all_funcs, set_of_function_names


def parse_files(list_of_files):
    # type: (List[str]) -> Tuple[Any, List[Any]]
    """
    Use Clang to parse the provided list of files, and return
    a tuple of the Clang index, and the list of compiled ASTs
    (one for each compilation unit)
    """
    idx = Index.create()
    t_units = []  # type: List[Any]

    # To avoid parsing the files all the time, store the parsed ASTs
    # of each compilation unit in a cache.
    if not os.path.exists(".cache"):
        os.mkdir(".cache")
    for filename in list_of_files:
        cache_filename = '.cache/' + os.path.basename(filename) + "_cache"
        # Have I parsed this file before?
        if os.path.exists(cache_filename):
            # Yes, load from cache
            try:
                t_units.append(
                    TranslationUnit.from_ast_file(
                        cache_filename, idx))
                print("[-] Loading cached AST for", filename)
            except TranslationUnitLoadError:
                print("[-] Parsing", filename)
                t_units.append(idx.parse(filename))
                t_units[-1].save(cache_filename)
        else:
            # No, parse it now.
            print("[-] Parsing", filename)
            t_units.append(idx.parse(filename))
            t_units[-1].save(cache_filename)
    return idx, t_units


def main():
    """
    Parse all passed-in C files (preprocessed with -E, to be standalone)
    and create call graphs and list of functions. Then scout for mentions
    of functions at any place, to collect the actually used functions.

    Finally, report the unused ones.
    """
    idx, t_units = parse_files(sys.argv[1:])

    # To avoid parsing all the time, store the list of functions
    # and the call graph in a local cache (the 1st time they are computed)
    #
    # Are all caches populated?
    if all(os.path.exists(x)
           for x in [CACHE_FUNCTION_NAMES, CACHE_CALL_GRAPH]):
        # Yes, get data from caches
        call_graph, set_of_function_names = (
            pickle.load(open(CACHE_CALL_GRAPH)),
            pickle.load(open(CACHE_FUNCTION_NAMES)))
    else:
        # No, it's time to parse the input C files and create the data.
        def no_work(_):
            pass
        call_graph, set_of_function_names = parse_calls(idx, t_units, no_work)
        # Save the parsed information in the two caches
        pickle.dump(call_graph, open(CACHE_CALL_GRAPH, "w"))
        pickle.dump(set_of_function_names, open(CACHE_FUNCTION_NAMES, "w"))

    used_functions = set()  # type: Set[str]

    def collect_function_mentions(node):
        """
        To find the unused functions, we need to collect all 'mentions'
        of functions anywhere. This is generally speaking, a hard problem.
        But... (see below)
        """
        if node.kind == CursorKind.TRANSLATION_UNIT:
            return

        for token in node.get_tokens():
            # But we can apply a simple heuristic: look at the tokens that
            # appear in a translation unit - and check if you find a mention
            # of a function (in the global set, which we've computed by now)
            # If so, mark this as a 'used' function.
            potential_func_name = token.spelling.strip()
            # Avoid including the function definition as a 'usage'
            if potential_func_name != node.spelling \
                    and potential_func_name in set_of_function_names \
                    and potential_func_name not in used_functions:
                print('[#]', potential_func_name, 'is mentioned in',
                      node.spelling, 'at', node.location)
                used_functions.add(potential_func_name)

    # To debug what happens with a specific compilation unit, use this:
    #
    # le_units = [x for x in t_units if x.spelling.endswith('svc191vnir.c')]
    # import ipdb ; ipdb.set_trace()
    # unused_1, unused_2 = \
    #     parse_calls(idx, le_units, collect_function_mentions)

    unused_1, unused_2 = \
        parse_calls(idx, t_units, collect_function_mentions)
    open('usedFunctions', 'w').write('\n'.join(sorted(used_functions)))


if __name__ == "__main__":
    main()
