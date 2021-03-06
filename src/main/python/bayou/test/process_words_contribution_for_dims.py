import sys
import json
import numpy as np

input_file = sys.argv[1]
#output_file = sys.argv[2]
# preferred to set 20
threshold = int(sys.argv[2])
# preferred 10
low_frequency = int(sys.argv[3])

print('reading file')
with open(input_file) as f:
    outputs = json.load(f)['outputs']

print('making vocabulary')
chars = set()
for opt in outputs:
    chars.update(opt['words'].split())
chars = list(chars)
vocab = dict(zip(chars, range(len(chars))))
vocab_size = len(vocab)

### Things remain the same for above.

print('making count table')
latent_size = len(outputs[0]['out_latent_dims'])
print('latent size is {}'.format(latent_size))
table = np.zeros([vocab_size, latent_size])
occurs = np.zeros([vocab_size])

print('filling count table')
for opt in outputs:
    words_list = opt['words'].split()
    words_length = len(words_list)
    # increments word occurences
    for w in words_list:
        occurs[vocab[w]] = occurs[vocab[w]] + 1

    # list of latent_size lists (of words_length size)
    out_multi_outputs = opt['out_multi_outputs']
    # fills value table
    for i in range(latent_size):
        for j, w in enumerate(words_list):
            table[vocab[w]][i] += out_multi_outputs[i][j]


print('normalize count table')
for i in range(vocab_size):
    if occurs[i] != 0:
        table[i] = table[i] / occurs[i]
        # only how frequent words
        if occurs[i] < low_frequency:
            table[i].fill(0)

print('transpose the table')
table = np.transpose(table)

### good so far

print('sort and output top members')
for i in range(latent_size):
    # in ascending order
    sorted_indices = np.argsort(table[i])
    top_members = [chars[idx] for idx in sorted_indices[vocab_size - threshold:].tolist()]
    top_members.reverse()
    top_members_scores = [table[i][vocab[w]] for w in top_members]
    print('for dimension{}, top {} words are:'.format(i, threshold))
    print(top_members)
    print(top_members_scores)
    # picked up negative numbers
    bottom_members = [chars[idx] for idx in sorted_indices[:threshold].tolist()]
    bottom_members_scores = [table[i][vocab[w]] for w in bottom_members]
    print('for dimension{}, bottom {} words are:'.format(i, threshold))
    print(bottom_members)
    print(bottom_members_scores)

