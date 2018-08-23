# Copyright 2017 Rice University
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function
import argparse
import sys
import json
import math
import random
import numpy as np
from itertools import chain

import ast_extractor

HELP = """Use this script to extract evidences from a raw data file with sequences generated by driver.
You can also filter programs based on number and length of sequences, and control the samples from each program."""


def extract_evidence(clargs):
    #print('Loading data file...')
    with open(clargs.input_file[0]) as f:
        js = json.load(f)
    #print('Done')
    done = 0
    programs = []

    ''' Program_dict dictionary holds Key values in format
    (Key = File_Name Value = dict(Key = String Method_Name, Value = [String ReturnType, List[String] FormalParam , List[String] Sequences] ))
    '''
    programs_dict = dict()


    valid = []
    #This part appends sorrounding evidences
    done = 0
    ignored = 0
    for program in js['programs']:
        try:
            ast_node_graph, ast_paths = ast_extractor.get_ast_paths(program['ast']['_nodes'])
            ast_extractor.validate_sketch_paths(program, ast_paths, clargs.max_ast_depth)

            file_name = program['file']
            method_name = program['method']

            sequences = program['sequences']
            returnType = program['returnType'] if 'returnType' in program else "void"
            formalParam = program['formalParam'] if 'formalParam' in program else []

            if len(sequences) > clargs.max_seqs or (len(sequences) == 1 and len(sequences[0]['calls']) == 1) or \
                any([len(sequence['calls']) > clargs.max_seq_length for sequence in sequences]):
                    raise ast_extractor.TooLongPathError


            if file_name not in programs_dict:
                programs_dict[file_name] = dict()

            if method_name not in programs_dict[file_name]:
                programs_dict[file_name][method_name] = [returnType, formalParam, sequences]
            else:
                # Choose the MethodDeclaration with lowest number of nodes in sequences, the reason being you want to
                # ignore the calls from constructor, as it is present in every sorrounding sequence, and also this target_link_libraries
                # care of the problem of having multiple constructors while extracting from DOM Driver, where you basically  extract multiple
                # copies of same method. However they appear in the data as we again iterate over js[programs]
                if numNodesInSequences(sequences) < numNodesInSequences(programs_dict[file_name][method_name][2]):
                    programs_dict[file_name][method_name] = [returnType, formalParam, sequences]


        except (ast_extractor.TooLongPathError, ast_extractor.InvalidSketchError) as e:
            ignored += 1
            #valid.append(False)

        done += 1
        #print('Extracted evidences of sorrounding features for {} programs'.format(done), end='\r')

    #print('')

    #print('{:8d} programs/asts in training data'.format(done))
    #print('{:8d} programs/asts ignored by given config'.format(ignored))
    #print('{:8d} programs/asts to search over'.format(done - ignored))


    done = 0
    for pid, program in enumerate(js['programs']):

        if '__PDB_FILL__' not in program['body']:
            continue

        calls = gather_calls(program['ast'])
        apicalls = list(set(chain.from_iterable([APICallsFromCall(call)
                                                 for call in calls])))
        types = list(set(chain.from_iterable([TypesFromCall(call)
                                              for call in calls])))
        keywords = list(set(chain.from_iterable([KeywordsFromCall(call)
                                                for call in calls])))
												
        file_name = program['file']
        method_name = program['method']

        sequences = program['sequences']
        returnType = program['returnType'] if 'returnType' in program else "void"
        formalParam = program['formalParam'] if 'formalParam' in program else []

        # Take in classTypes and sample a few
        classTypes = program['classTypes'] if 'classTypes' in program else []
        random.shuffle(classTypes)

        sample = dict(program)
        sample['sorrreturntype'] = []
        sample['sorrformalparam'] = []
        sample['sorrsequences'] = []
        sample['classTypes'] = classTypes
        sample['apicalls'] = apicalls
        sample['types'] = types
        sample['keywords'] = keywords


        #    (Key = File_Name Value = dict(Key = String Method_Name, Value = [String ReturnType, List[String] FormalParam , List[String] Sequences] ))
        otherMethods = list(programs_dict[file_name].keys())
        random.shuffle(otherMethods)

        countSorrMethods = 0
        for method in otherMethods: # Each iterator is a method Name with @linenumber

            # Ignore the current method from list of sorrounding methods
            if method == method_name:
                continue
            # Keep a count on number of sorrounding methods, if it exceeds the random choice, break
            countSorrMethods += 1


            for choice, evidence in zip(programs_dict[file_name][method],['sorrreturntype', 'sorrformalparam', 'sorrsequences']):
                sample[evidence].append(choice)

        programs.append(sample)

        done += 1
        print('Extracted evidence for {} programs'.format(done), end='\r')

    #random.shuffle(programs)


    #print('\nWriting to {}...'.format(clargs.output_file[0]), end='')
    with open(clargs.output_file[0], 'w') as f:
        json.dump({'programs': programs}, fp=f, indent=2)
    #print('done')



def numNodesInSequences(sequences):
    totLen = 0
    for elem in sequences:
        totLen += len(elem['calls'])
    return totLen

def APICallsFromCall(callnode):
	call = callnode['_call']
	call = re.sub('^\$.*\$', '', call)  # get rid of predicates
	name = call.split('(')[0].split('.')[-1]
	name = name.split('<')[0]  # remove generics from call name
	return [name] if name[0].islower() else []  # Java convention

def get_types_re(s):
	patt = re.compile('java[x]?\.(\w*)\.(\w*)(\.([A-Z]\w*))*')
	types = [match.group(4) if match.group(4) is not None else match.group(2)
			 for match in re.finditer(patt, s)]
	primitives = {
		'byte': 'Byte',
		'short': 'Short',
		'int': 'Integer',
		'long': 'Long',
		'float': 'Float',
		'double': 'Double',
		'boolean': 'Boolean',
		'char': 'Character'
	}

	for p in primitives:
		if s == p or re.search('\W{}'.format(p), s):
			types.append(primitives[p])
	return list(set(types))
	
def TypesFromCall(callnode):
	call = callnode['_call']
	types = get_types_re(call)

	if '_throws' in callnode:
		for throw in callnode['_throws']:
			types += get_types_re(throw)

	if '_returns' in callnode:
		types += get_types_re(callnode['_returns'])

	return list(set(types))

Keywords_STOP_WORDS = {  # CoreNLP English stop words
        "'ll", "'s", "'m", "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
        "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between",
        "both", "but", "by", "can", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does",
        "doesn't", "doing", "don't", "down", "during", "each", "few", "for", "from", "further", "had",
        "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
        "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll",
        "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's", "me",
        "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only",
        "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
        "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such", "than", "that", "that's",
        "the", "their", "theirs", "them", "themselves", "then", "there", "there's", "these", "they",
        "they'd", "they'll", "they're", "they've", "this", "those", "through", "to", "too", "under",
        "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "weren't",
        "what", "what's", "when", "when's", "where", "where's", "which", "while", "who", "who's", "whom",
        "why", "why's", "with", "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've",
        "your", "yours", "yourself", "yourselves", "return", "arent", "cant", "couldnt", "didnt", "doesnt",
        "dont", "hadnt", "hasnt", "havent", "hes", "heres", "hows", "im", "isnt", "its", "lets", "mustnt",
        "shant", "shes", "shouldnt", "thats", "theres", "theyll", "theyre", "theyve", "wasnt", "were",
        "werent", "whats", "whens", "wheres", "whos", "whys", "wont", "wouldnt", "youd", "youll", "youre",
        "youve"
    }

def Keywords_split_camel(s):
	s = re.sub('(.)([A-Z][a-z]+)', r'\1#\2', s)  # UC followed by LC
	s = re.sub('([a-z0-9])([A-Z])', r'\1#\2', s)  # LC followed by UC
	return s.split('#')
	
def KeywordsFromCall(callnode):
	call = callnode['_call']
	call = re.sub('^\$.*\$', '', call)  # get rid of predicates
	qualified = call.split('(')[0]
	qualified = re.sub('<.*>', '', qualified).split('.')  # remove generics for keywords

	# add qualified names (java, util, xml, etc.), API calls and types
	keywords = list(chain.from_iterable([Keywords_split_camel(s) for s in qualified])) + \
		list(chain.from_iterable([Keywords_split_camel(c) for c in APICallsFromCall(callnode)])) + \
		list(chain.from_iterable([Keywords_split_camel(t) for t in TypesFromCall(callnode)]))

	# convert to lower case, omit stop words and take the set
	return list(set([k.lower() for k in keywords if k.lower() not in Keywords_STOP_WORDS]))

def gather_calls(node):
    """
    Gathers all call nodes (recursively) in a given AST node

    :param node: the node to gather calls from
    :return: list of call nodes
    """

    if type(node) is list:
        return list(chain.from_iterable([gather_calls(n) for n in node]))
    node_type = node['node']
    if node_type == 'DSubTree':
        return gather_calls(node['_nodes'])
    elif node_type == 'DBranch':
        return gather_calls(node['_cond']) + gather_calls(node['_then']) + gather_calls(node['_else'])
    elif node_type == 'DExcept':
        return gather_calls(node['_try']) + gather_calls(node['_catch'])
    elif node_type == 'DLoop':
        return gather_calls(node['_cond']) + gather_calls(node['_body'])
    else:  # this node itself is a call
        return [node]




if __name__ == '__main__':
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=HELP)
    parser.add_argument('input_file', type=str, nargs=1,
                        help='input data file')
    parser.add_argument('output_file', type=str, nargs=1,
                        help='output data file')
    parser.add_argument('--python_recursion_limit', type=int, default=10000,
                        help='set recursion limit for the Python interpreter')
    parser.add_argument('--max_seqs', type=int, default=9999,
                        help='maximum number of sequences in a program')
    parser.add_argument('--max_seq_length', type=int, default=9999,
                        help='maximum length of each sequence in a program')
    parser.add_argument('--max_ast_depth', type=int, default=32,
                        help='maximum depth of decoder')

    clargs = parser.parse_args()
    sys.setrecursionlimit(clargs.python_recursion_limit)

    extract_evidence(clargs)
