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

import tensorflow as tf
import numpy as np
import os
import re
import json
import nltk
from itertools import chain
from collections import Counter
from nltk.stem.wordnet import WordNetLemmatizer

from bayou.models.low_level_evidences.utils import CONFIG_ENCODER, CONFIG_INFER, C0, UNK
from tensorflow.python.ops import embedding_ops


class Evidence(object):

    def init_config(self, evidence, chars_vocab):
        for attr in CONFIG_ENCODER + (CONFIG_INFER if chars_vocab else []):
            self.__setattr__(attr, evidence[attr])

    def dump_config(self):
        js = {attr: self.__getattribute__(attr) for attr in CONFIG_ENCODER + CONFIG_INFER}
        return js

    @staticmethod
    def read_config(js, chars_vocab):
        evidences = []
        for evidence in js:
            name = evidence['name']
            if name == 'apicalls':
                e = APICalls()
            elif name == 'types':
                e = Types()
            elif name == 'keywords':
                e = Keywords()
            elif name == 'javadoc':
                e = Javadoc()
            else:
                raise TypeError('Invalid evidence name: {}'.format(name))
            e.init_config(evidence, chars_vocab)
            evidences.append(e)
        return evidences

    def read_data_point(self, program):
        raise NotImplementedError('read_data() has not been implemented')

    def set_chars_vocab(self, data):
        raise NotImplementedError('set_chars_vocab() has not been implemented')

    def wrangle(self, data):
        raise NotImplementedError('wrangle() has not been implemented')

    def placeholder(self, config):
        raise NotImplementedError('placeholder() has not been implemented')

    def exists(self, inputs):
        raise NotImplementedError('exists() has not been implemented')

    def init_sigma(self, config):
        raise NotImplementedError('init_sigma() has not been implemented')

    def encode(self, inputs, config):
        raise NotImplementedError('encode() has not been implemented')

    def evidence_loss(self, psi, encoding, config):
        raise NotImplementedError('evidence_loss() has not been implemented')


class APICalls(Evidence):

    def read_data_point(self, program):
        apicalls = program['apicalls'] if 'apicalls' in program else []
        return list(set(apicalls))

    def set_chars_vocab(self, data):
        counts = Counter([c for apicalls in data for c in apicalls])
        self.chars = sorted(counts.keys(), key=lambda w: counts[w], reverse=True)
        self.vocab = dict(zip(self.chars, range(len(self.chars))))
        self.vocab_size = len(self.vocab)

    def wrangle(self, data):
        wrangled = np.zeros((len(data), 1, self.vocab_size), dtype=np.int32)
        for i, apicalls in enumerate(data):
            for c in apicalls:
                if c in self.vocab:
                    wrangled[i, 0, self.vocab[c]] = 1
        return wrangled

    def placeholder(self, config):
        return tf.placeholder(tf.float32, [config.batch_size, 1, self.vocab_size])

    def exists(self, inputs):
        i = tf.reduce_sum(inputs, axis=2)
        return tf.not_equal(tf.count_nonzero(i, axis=1), 0)

    def init_sigma(self, config):
        with tf.variable_scope('apicalls'):
            self.sigma = tf.get_variable('sigma', [])

    def encode(self, inputs, config):
        with tf.variable_scope('apicalls'):
            latent_encoding = tf.zeros([config.batch_size, config.latent_size])
            inp = tf.slice(inputs, [0, 0, 0], [config.batch_size, 1, self.vocab_size])
            inp = tf.reshape(inp, [-1, self.vocab_size])
            encoding = tf.layers.dense(inp, self.units, activation=tf.nn.tanh)
            for i in range(self.num_layers - 1):
                encoding = tf.layers.dense(encoding, self.units, activation=tf.nn.tanh)
            w = tf.get_variable('w', [self.units, config.latent_size])
            b = tf.get_variable('b', [config.latent_size])
            latent_encoding += tf.nn.xw_plus_b(encoding, w, b)
            return latent_encoding

    def evidence_loss(self, psi, encoding, config):
        sigma_sq = tf.square(self.sigma)
        loss = 0.5 * (config.latent_size * tf.log(2 * np.pi * sigma_sq + 1e-10)
                      + tf.square(encoding - psi) / sigma_sq)
        return loss

    @staticmethod
    def from_call(callnode):
        call = callnode['_call']
        call = re.sub('^\$.*\$', '', call)  # get rid of predicates
        name = call.split('(')[0].split('.')[-1]
        name = name.split('<')[0]  # remove generics from call name
        return [name] if name[0].islower() else []  # Java convention


class Types(Evidence):

    def read_data_point(self, program):
        types = program['types'] if 'types' in program else []
        return list(set(types))

    def set_chars_vocab(self, data):
        counts = Counter([t for types in data for t in types])
        self.chars = sorted(counts.keys(), key=lambda w: counts[w], reverse=True)
        self.vocab = dict(zip(self.chars, range(len(self.chars))))
        self.vocab_size = len(self.vocab)

    def wrangle(self, data):
        wrangled = np.zeros((len(data), 1, self.vocab_size), dtype=np.int32)
        for i, types in enumerate(data):
            for t in types:
                if t in self.vocab:
                    wrangled[i, 0, self.vocab[t]] = 1
        return wrangled

    def placeholder(self, config):
        return tf.placeholder(tf.float32, [config.batch_size, 1, self.vocab_size])

    def exists(self, inputs):
        i = tf.reduce_sum(inputs, axis=2)
        return tf.not_equal(tf.count_nonzero(i, axis=1), 0)

    def init_sigma(self, config):
        with tf.variable_scope('types'):
            self.sigma = tf.get_variable('sigma', [])

    def encode(self, inputs, config):
        with tf.variable_scope('types'):
            latent_encoding = tf.zeros([config.batch_size, config.latent_size])
            inp = tf.slice(inputs, [0, 0, 0], [config.batch_size, 1, self.vocab_size])
            inp = tf.reshape(inp, [-1, self.vocab_size])
            encoding = tf.layers.dense(inp, self.units, activation=tf.nn.tanh)
            for i in range(self.num_layers - 1):
                encoding = tf.layers.dense(encoding, self.units, activation=tf.nn.tanh)
            w = tf.get_variable('w', [self.units, config.latent_size])
            b = tf.get_variable('b', [config.latent_size])
            latent_encoding += tf.nn.xw_plus_b(encoding, w, b)
            return latent_encoding

    def evidence_loss(self, psi, encoding, config):
        sigma_sq = tf.square(self.sigma)
        loss = 0.5 * (config.latent_size * tf.log(2 * np.pi * sigma_sq + 1e-10)
                      + tf.square(encoding - psi) / sigma_sq)
        return loss

    @staticmethod
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

    @staticmethod
    def from_call(callnode):
        call = callnode['_call']
        types = Types.get_types_re(call)

        if '_throws' in callnode:
            for throw in callnode['_throws']:
                types += Types.get_types_re(throw)

        if '_returns' in callnode:
            types += Types.get_types_re(callnode['_returns'])

        return list(set(types))


class Keywords(Evidence):
    def __init__(self):
        nltk.download('wordnet')
        self.lemmatizer = WordNetLemmatizer()

    STOP_WORDS = {  # CoreNLP English stop words
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

    def lemmatize(self, word):
        w = self.lemmatizer.lemmatize(word, 'v')
        return self.lemmatizer.lemmatize(w, 'n')

    def read_data_point(self, program):
        keywords = [self.lemmatize(k) for k in program['keywords']] if 'keywords' in program else []
        return list(set(keywords))

    def set_chars_vocab(self, data):
        counts = Counter([c for keywords in data for c in keywords])
        self.chars = sorted(counts.keys(), key=lambda w: counts[w], reverse=True)
        self.vocab = dict(zip(self.chars, range(len(self.chars))))
        self.vocab_size = len(self.vocab)

    def wrangle(self, data):
        wrangled = np.zeros((len(data), 1, self.vocab_size), dtype=np.int32)
        for i, keywords in enumerate(data):
            for k in keywords:
                if k in self.vocab and k not in Keywords.STOP_WORDS:
                    wrangled[i, 0, self.vocab[k]] = 1
        return wrangled

    def placeholder(self, config):
        return tf.placeholder(tf.float32, [config.batch_size, 1, self.vocab_size])

    def exists(self, inputs):
        i = tf.reduce_sum(inputs, axis=2)
        return tf.not_equal(tf.count_nonzero(i, axis=1), 0)

    def init_sigma(self, config):
        with tf.variable_scope('keywords'):
            self.sigma = tf.get_variable('sigma', [])

    def encode(self, inputs, config):
        with tf.variable_scope('keywords'):
            latent_encoding = tf.zeros([config.batch_size, config.latent_size])
            inp = tf.slice(inputs, [0, 0, 0], [config.batch_size, 1, self.vocab_size])
            inp = tf.reshape(inp, [-1, self.vocab_size])
            encoding = tf.layers.dense(inp, self.units, activation=tf.nn.tanh)
            for i in range(self.num_layers - 1):
                encoding = tf.layers.dense(encoding, self.units, activation=tf.nn.tanh)
            w = tf.get_variable('w', [self.units, config.latent_size])
            b = tf.get_variable('b', [config.latent_size])
            latent_encoding += tf.nn.xw_plus_b(encoding, w, b)
            return latent_encoding

    def evidence_loss(self, psi, encoding, config):
        sigma_sq = tf.square(self.sigma)
        loss = 0.5 * (config.latent_size * tf.log(2 * np.pi * sigma_sq + 1e-10)
                      + tf.square(encoding - psi) / sigma_sq)
        return loss

    @staticmethod
    def split_camel(s):
        s = re.sub('(.)([A-Z][a-z]+)', r'\1#\2', s)  # UC followed by LC
        s = re.sub('([a-z0-9])([A-Z])', r'\1#\2', s)  # LC followed by UC
        return s.split('#')

    @staticmethod
    def from_call(callnode):
        call = callnode['_call']
        call = re.sub('^\$.*\$', '', call)  # get rid of predicates
        qualified = call.split('(')[0]
        qualified = re.sub('<.*>', '', qualified).split('.')  # remove generics for keywords

        # add qualified names (java, util, xml, etc.), API calls and types
        keywords = list(chain.from_iterable([Keywords.split_camel(s) for s in qualified if s not in ['java', 'javax']])) + \
            list(chain.from_iterable([Keywords.split_camel(c) for c in APICalls.from_call(callnode)])) + \
            list(chain.from_iterable([Keywords.split_camel(t) for t in Types.from_call(callnode)]))

        # convert to lower case, omit stop words and take the set
        return list(set([k.lower() for k in keywords if k.lower() not in Keywords.STOP_WORDS]))


class Javadoc(Evidence):
    STOP_WORDS = {  # CoreNLP English stop words
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

    CONFIG_ADD = ['max_words', 'embed_dim', 'rnn_units']

    def init_config(self, evidence, chars_vocab):
        for attr in CONFIG_ENCODER + Javadoc.CONFIG_ADD + (CONFIG_INFER if chars_vocab else []):
            self.__setattr__(attr, evidence[attr])

    def dump_config(self):
        js = {attr: self.__getattribute__(attr) for attr in CONFIG_ENCODER + Javadoc.CONFIG_ADD + CONFIG_INFER}
        return js

    def read_data_point(self, program):
        # special treatment of empty javadoc
        javadoc = program['javadoc'] if 'javadoc' in program else []
        # reverse the sentence
        return javadoc.split()[::-1]

    # good, universally used
    def set_chars_vocab(self, embedding_file):
        self.chars = []
        self.chars.append('<unk>')
        self.vocab_embeddings = []
        file = open(embedding_file)
        for line in file.readlines():
            row = line.strip().split()
            self.chars.append(row[0])
            self.vocab_embeddings.append(row[1:])
        self.vocab = dict(zip(self.chars, range(len(self.chars))))
        self.vocab_size = len(self.vocab)
        self.vocab_embeddings.insert(0, np.random.rand(self.embed_dim))
        self.vocab_embeddings = np.asarray(self.vocab_embeddings, np.float32)

    # def wrangle(self, data):
    #     wrangled = np.zeros((len(data), 1, self.vocab_size), dtype=np.int32)
    #     for i, keywords in enumerate(data):
    #         for k in keywords:
    #             if k in self.vocab and k not in Keywords.STOP_WORDS:
    #                 wrangled[i, 0, self.vocab[k]] = 1
    #     return wrangled

    def wrangle(self, data):
        wrangled = np.zeros((len(data), self.max_words + 1), dtype=np.int32)
        for i, words in enumerate(data):
            cursor = 0
            for w in words:
                if w in self.vocab and w not in Javadoc.STOP_WORDS and cursor < self.max_words:
                    wrangled[i, cursor] = self.vocab[w]
                    cursor += 1
            wrangled[i, self.max_words] = cursor
        return wrangled

    # def placeholder(self, config):
    #     return tf.placeholder(tf.float32, [config.batch_size, 1, self.vocab_size])

    def placeholder(self, config):
        # 21 = max_words(20) + words_len(1)
        return tf.placeholder(tf.float32, [config.batch_size, self.max_words + 1])

    # def exists(self, inputs):
    #     i = tf.reduce_sum(inputs, axis=2)
    #     return tf.not_equal(tf.count_nonzero(i, axis=1), 0)

    # check instances in the batch being zero
    def exists(self, inputs):
        # corner very unlikely case, all latent-size non-zero numbers sum to one
        i = tf.reduce_sum(inputs, axis=1)
        return tf.not_equal(i, 0)

    def init_sigma(self, config):
        with tf.variable_scope('javadoc'):
            self.sigma = tf.get_variable('sigma', [])

    def encode(self, inputs, config):
        # inputs.shape=(batch_size, max_words+1)
        inputs = tf.cast(inputs, tf.int32)
        with tf.variable_scope('javadoc'):
            if hasattr(self, 'vocab_embeddings'):
                embeddings_initializer = tf.constant_initializer(self.vocab_embeddings)
                embedding_var = tf.get_variable(
                    name='embeddings',
                    shape=(self.vocab_size, self.embed_dim),
                    initializer=embeddings_initializer,
                    trainable=False)
            else:
                embedding_var = tf.get_variable(name='embeddings', shape=(self.vocab_size, self.embed_dim),
                                                trainable=False)
            # (batch_size, max_words), (batch_size, 1)
            words, lengths_2d = tf.split(inputs, [self.max_words, 1], 1)
            # (batch_size, max_words, embed_dim)
            encoder_emb_input = embedding_ops.embedding_lookup(embedding_var, words)

            cell_fw = tf.nn.rnn_cell.GRUCell(self.rnn_units)
            cell_bw = tf.nn.rnn_cell.GRUCell(self.rnn_units)
            lengths_1d = tf.reshape(lengths_2d, shape=[config.batch_size])
            # outputs=(output_fw, output_bw), [batch_size, max_time, cell_{f/b}w.output_size]
            outputs, _ = tf.nn.bidirectional_dynamic_rnn(cell_fw, cell_bw, inputs=encoder_emb_input, dtype=tf.float32,
                                                         sequence_length=lengths_1d)
            # (batch_size, max_time, cell_fw.output_size+cell_bw.output_size)
            brnn_outputs = tf.concat(outputs, axis=2)

            # zero out the regions beyond sequences lengths using sequence masking
            # zero out is not necessary due to the properties of bidirectional_dynamic_rnn

            latent_dims = []
            softmax_input_layers = 3
            non_softmax_input_layers = 3

            # for getting local tensor values while predicting and checking
            self.multi_outputs = []
            self.softmax_outputs = []

            for i in range(config.latent_size):
                with tf.variable_scope('encoder_attention_' + str(i)):
                    # prepare softmax input
                    softmax_input = brnn_outputs
                    for j in range(softmax_input_layers - 1):
                        softmax_input = tf.layers.dense(softmax_input, self.rnn_units * 2, tf.nn.tanh)
                    # (batch_size, max_time, 1)
                    softmax_input_scalar = tf.layers.dense(softmax_input, 1)
                    # reshape, (batch_size, max_time)
                    softmax_input_scalar_squeeze = tf.squeeze(softmax_input_scalar, axis=2)
                    # mask for inputs beyond actual timesteps, (batch_size, max_time)
                    mask_flag = tf.sequence_mask(lengths_1d, tf.shape(softmax_input_scalar_squeeze)[1])
                    # inf_mask = tf.tile(tf.Variable([[-1000000.0]]), tf.Variable([config.batch_size, self.max_words]))
                    inf_mask = tf.constant(-1000000.0, shape=[config.batch_size, self.max_words])
                    softmax_input_scalar_mask = tf.where(mask_flag, softmax_input_scalar_squeeze, inf_mask)
                    # (batch_size, max_time)
                    softmax_output = tf.nn.softmax(softmax_input_scalar_mask)

                    # prepare another non-softmax input to the multiplication operation
                    non_softmax_input = brnn_outputs
                    for j in range(non_softmax_input_layers - 1):
                        non_softmax_input = tf.layers.dense(non_softmax_input, self.rnn_units * 2, tf.nn.tanh)
                    non_softmax_input_scalar = tf.layers.dense(non_softmax_input, 1, tf.nn.tanh)
                    # (batch_size, max_time)
                    non_softmax_input_scalar_squeeze = tf.squeeze(non_softmax_input_scalar, axis=2)
                    non_softmax_input_scalar_squeeze = tf.where(mask_flag, non_softmax_input_scalar_squeeze,
                                                                tf.zeros_like(non_softmax_input_scalar_squeeze))

                    # multiplication (batch_size, max_time)
                    multi_output = softmax_output * non_softmax_input_scalar_squeeze
                    self.multi_outputs.append(multi_output)
                    self.softmax_outputs.append(softmax_output)

                    # reduce_sum, last dimension, (batch_size)
                    latent_dim = tf.reduce_sum(multi_output, -1)
                    latent_dims.append(latent_dim)

            # for getting local tensor values while predicting and checking
            self.latent_dims = latent_dims

            # concatenate latent_dims, (batch_size, latent_size)
            latent_vector = tf.stack(latent_dims, axis=1)
            return latent_vector


    def evidence_loss(self, psi, encoding, config):
        sigma_sq = tf.square(self.sigma)
        loss = 0.5 * (config.latent_size * tf.log(2 * np.pi * sigma_sq + 1e-10)
                      + tf.square(encoding - psi) / sigma_sq)
        return loss

    @staticmethod
    def split_camel(s):
        s = re.sub('(.)([A-Z][a-z]+)', r'\1#\2', s)  # UC followed by LC
        s = re.sub('([a-z0-9])([A-Z])', r'\1#\2', s)  # LC followed by UC
        return s.split('#')

    @staticmethod
    def from_call(callnode):
        call = callnode['_call']
        call = re.sub('^\$.*\$', '', call)  # get rid of predicates
        qualified = call.split('(')[0]
        qualified = re.sub('<.*>', '', qualified).split('.')  # remove generics for keywords

        # add qualified names (java, util, xml, etc.), API calls and types
        keywords = list(chain.from_iterable([Keywords.split_camel(s) for s in qualified])) + \
                   list(chain.from_iterable([Keywords.split_camel(c) for c in APICalls.from_call(callnode)])) + \
                   list(chain.from_iterable([Keywords.split_camel(t) for t in Types.from_call(callnode)]))

        # convert to lower case, omit stop words and take the set
        return list(set([k.lower() for k in keywords if k.lower() not in Keywords.STOP_WORDS]))
