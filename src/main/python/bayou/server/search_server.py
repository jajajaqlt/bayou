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
#


from __future__ import print_function
import numpy as np
import tensorflow as tf

import argparse
import os
import sys
import json
import textwrap

import time
import bayou.models.low_level_evidences.infer
from bayou.models.low_level_evidences.utils import read_config
from bayou.models.low_level_evidences.data_reader import Reader


File_Name = 'Search_Data_Basic'

HELP = """ Help me! :( """
#%%


def search_server(clargs):
    #set clargs.continue_from = True while testing, it continues from old saved config
    clargs.continue_from = True

    model = bayou.models.low_level_evidences.infer.BayesianPredictor


    # load the saved config
    with open(os.path.join(clargs.save, 'config.json')) as f:
        config = read_config(json.load(f), chars_vocab=True)

    config.num_batches = 1
    config.batch_size = 1

    with tf.Session() as sess:
        predictor = model(clargs.save, sess, config, bayou_mode = False) # goes to infer.BayesianPredictor



        reader = Reader(clargs, config, infer=True)
        _prog_ids, ev_data, n, e, y, jsp = reader.next_batch()
        reader.reset_batches()
        _, a1, b1, _, _ = predictor.get_all_params_inago(ev_data, n, e, y)

        programs = []
        program = jsp[0]
        # We do not need other paths in the program as all the evidences are the same for all the paths
        # and for new test code we are only interested in the evidence encodings
        # a1, a2 and ProbY are all scalars, b1 and b2 are vectors
        program['a1'] = a1[0].item() # .item() converts a numpy element to a python element, one that is JSON serializable
        program['b1'] = [val.item() for val in b1[0]]
        program['a2'] = None
        program['b2'] = None
        program['ProbY'] = None

        programs.append(program)

        print('\nWriting to {}...'.format('/home/ubuntu/QueryProgWEncoding.json'), end='\n')
        with open('/home/ubuntu/QueryProgWEncoding.json', 'w') as f:
            json.dump({'programs': programs}, fp=f, indent=2)
        print('done')




    return



#%%
if __name__ == '__main__':
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=textwrap.dedent(HELP))
    parser.add_argument('input_file', type=str, nargs=1,
                        help='input data file')
    parser.add_argument('--python_recursion_limit', type=int, default=10000,
                        help='set recursion limit for the Python interpreter')
    parser.add_argument('--save', type=str, default='savedSearchModel',
                        help='checkpoint model during training here')
    parser.add_argument('--evidence', type=str, default='all',
                        choices=['apicalls', 'types', 'keywords', 'all'],
                        help='use only this evidence for inference queries')
    parser.add_argument('--output_file', type=str, default=None,
                        help='output file to print probabilities')

    #clargs = parser.parse_args()
    clargs = parser.parse_args(
	[
     # '..\..\..\..\..\..\data\DATA-training-top.json'])
     #'/home/rm38/Research/Bayou_Code_Search/Corpus/DATA-training-expanded-biased-TOP.json'])
     # '/home/ubuntu/Corpus/DATA-training-expanded-biased.json'])
     '/home/ubuntu/QueryProg.json'])
    sys.setrecursionlimit(clargs.python_recursion_limit)
    search_server(clargs)
