#!/bin/bash

filename=$1
splits=$2

sed 's/^/big_data\/Corpus\//g' $filename > java_paths.txt
sed 's/$/\.json/g' java_paths.txt > json_paths.txt

export PYTHONPATH=/home/ubuntu/bayou/src/main/python

Nolines=($(wc -l json_paths.txt))
echo number of lines is $Nolines
split_share=$((Nolines / splits))
echo the share of each split is $split_share

for i in $(seq 1 $splits);
do
	echo $i
        start=$(((i-1)*split_share+1))
        if [ $i -eq $splits ]
        then
                end=$Nolines
        else
                end=$((i*split_share))
        fi
	echo start is $start, end is $end	
	sed -n "$start,$end p" json_paths.txt > json_paths-$i.txt
	python3 bayou/src/main/python/scripts/merge.py json_paths-$i.txt --output_file merge_out-$i.json
	python3 bayou/src/main/python/scripts/evidence_extractor.py merge_out-$i.json final_output-$i.json
done

