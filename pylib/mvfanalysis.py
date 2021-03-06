# -*- coding: utf-8 -*-
"""
MVFtools: Multisample Variant Format Toolkit
James B. Pease and Ben K. Rosenzweig
http://www.github.org/jbpease/mvftools

If you use this software please cite:
Pease JB and BK Rosenzweig. 2015.
"Encoding Data Using Biological Principles: the Multisample Variant Format
for Phylogenomics and Population Genomics"
IEEE/ACM Transactions on Computational Biology and Bioinformatics. In press.
http://www.dx.doi.org/10.1109/tcbb.2015.2509997

This file is part of MVFtools.

MVFtools is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
MVFtools is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with MVFtools.  If not, see <http://www.gnu.org/licenses/>.

"""

from random import randint
from itertools import combinations
from pylib.mvfbase import MultiVariantFile, OutputFile, zerodiv, same_window
from pylib.mvfbiolib import MvfBioLib

MLIB = MvfBioLib()


def check_mincoverage(val, alleles):
    """Check if site has minimum coverage"""
    if val is not None:
        if sum([int(x not in 'Xx-') for x in alleles]) < val:
            return False
    return True


def pi_diversity(seq):
    """Calculate Pi sequence diversity"""
    seq = ''.join([MLIB.splitbases[x] for x in seq])
    base_count = [seq.count(x) for x in 'ATGC']
    total = float(sum(base_count))
    if not total:
        return 'nodata'
    if any(x == total for x in base_count):
        return 0.0
    else:
        return total / (total - 1) * (1 - sum([(x / total)**2
                                               for x in base_count]))


def calc_sample_coverage(args):
    """Counts the total number of non-gap/ambiguous characters for
      each sample per contig.
      """
    mvf = MultiVariantFile(args.mvf, 'read')
    data = {}
    # Set up sample indices
    sample_labels = mvf.get_sample_labels()
    if args.sample_indices is not None:
        sample_indices = [int(x) for x in
                          args.sample_indices[0].split(",")]
    elif args.sample_labels is not None:
        sample_indices = mvf.get_sample_indices(
            labels=args.sample_labels[0].split(","))
    else:
        sample_indices = mvf.get_sample_indices()
    # Set up contig ids
    if args.contig_ids is not None:
        contig_ids = args.contig_ids[0].split(",")
    elif args.contig_labels is not None:
        contig_ids = mvf.get_contig_ids(
            labels=args.contig_labels[0].split(","))
    else:
        contig_ids = mvf.get_contig_ids()
    for contig, _, allelesets in mvf.iterentries(
            contigs=contig_ids, subset=sample_indices,
            decode=True):
        if contig not in data:
            data[contig] = dict.fromkeys(sample_labels, 0)
            data[contig]['contig'] = contig
        for j, x in enumerate(sample_indices):
            data[contig][sample_labels[x]] += int(
                allelesets[0][j] not in 'Xx-')
    outfile = OutputFile(path=args.out,
                         headers=(["contig"] + [sample_labels[x] for x in
                                                sample_indices]))
    for contig in data:
        outfile.write_entry(data[contig])
    return ''


def calc_dstat_combinations(args):
    """Calculate genome-wide D-statstics for
       all possible trio combinations of samples
       and outgroups specified.
    """
    mvf = MultiVariantFile(args.mvf, 'read')
    data = {}
    sample_labels = mvf.get_sample_labels()
    if args.outgroup_indices is not None:
        outgroup_indices = [int(x) for x in
                            args.outgroup_indices[0].split(",")]
    elif args.outgroup_labels is not None:
        outgroup_indices = mvf.get_sample_indices(
            labels=args.outgroup_labels[0].split(","))
    if args.sample_indices is not None:
        sample_indices = [int(x) for x in
                          args.sample_indices[0].split(",")]
    elif args.sample_labels is not None:
        sample_indices = mvf.get_sample_indices(
            labels=args.sample_labels[0].split(","))
    else:
        sample_indices = mvf.get_sample_indices()
    if args.contig_ids is not None:
        contig_ids = args.contig_ids[0].split(",")
    elif args.contig_labels is not None:
        contig_ids = mvf.get_contig_ids(
            labels=args.contig_labels[0].split(","))
    else:
        contig_ids = mvf.get_contig_ids()
    if any(x in outgroup_indices for x in sample_indices):
        raise RuntimeError("Sample and Outgroup column lists cannot overlap.")
    for contig, _, allelesets in mvf:
        if contig not in contig_ids:
            continue
        alleles = mvf.decode(allelesets[0])
        for i, j, k in combinations(sample_indices, 3):
            for outgroup in outgroup_indices:
                subset = [alleles[x] for x in
                          [i, j, k, outgroup]]
                if any(x not in 'ATGC' for x in subset):
                    continue
                if subset[-1] not in subset[:3]:
                    continue
                if len(set(subset)) != 2:
                    continue
                # [ABBA, BABA, BBAA]
                val = (0 +
                       1 * (subset[0] == subset[3]) +
                       2 * (subset[1] == subset[3]) +
                       4 * (subset[2] == subset[3]))
                if val == 1 or val == 2:
                    val -= 1
                elif val == 4:
                    val = 2
                else:
                    continue
                tetrad = (i, j, k, outgroup)
                if tetrad not in data:
                    data[tetrad] = {}
                if contig not in data[tetrad]:
                    data[tetrad][contig] = [0, 0, 0]
                data[tetrad][contig][val] += 1
    # WRITE OUTPUT
    headers = ['sample0', 'sample1', 'sample2', "outgroup"]
    for xcontig in contig_ids:
        headers.extend(['{}:abba'.format(xcontig),
                        '{}:baba'.format(xcontig),
                        '{}:bbaa'.format(xcontig),
                        '{}:D'.format(xcontig)
                        ])
    outfile = OutputFile(path=args.out, headers=headers)
    for i, j, k in combinations(sample_indices, 3):
        for outgroup in outgroup_indices:
            tetrad = tuple([i, j, k, outgroup])
            if tetrad not in data:
                continue
            entry = dict([('sample{}'.format(i),
                           sample_labels[x])
                          for i, x in enumerate(tetrad[:3])])
            entry['outgroup'] = sample_labels[outgroup]
            for contig in contig_ids:
                if contig not in data[tetrad]:
                    entry.update(dict().fromkeys([
                        '{}:abba'.format(contig),
                        '{}:baba'.format(contig),
                        '{}:bbaa'.format(contig),
                        '{}:D'.format(contig)], '0'))
                else:
                    [abba, baba, bbaa] = data[tetrad][contig]
                    if abba > baba and abba > bbaa:

                        dstat = zerodiv(baba - bbaa, baba + bbaa)
                    elif baba > bbaa and baba > abba:
                        dstat = zerodiv(abba - bbaa, abba + bbaa)
                    else:
                        dstat = zerodiv(abba - baba, abba + baba)
                    entry.update([('{}:abba'.format(contig), abba),
                                  ('{}:baba'.format(contig), baba),
                                  ('{}:bbaa'.format(contig), bbaa),
                                  ('{}:D'.format(contig), dstat)
                                  ])
            outfile.write_entry(entry)
    return ''


def calc_pattern_count(args):
    """Count biallelic patterns spatially along
       chromosomes (e.g,, for use in DFOIL or Dstats
       http://www.github.com/jbpease/dfoil).
       The last sample specified will determine the 'A'
       versus 'B' allele.
    """
    mvf = MultiVariantFile(args.mvf, 'read')
    data = {}
    current_contig = None
    current_position = 0
    sitepatterns = {}
    # sample_labels = mvf.get_sample_labels()
    if args.sample_indices is not None:
        sample_indices = [int(x) for x in
                          args.sample_indices[0].split(",")]
    elif args.sample_labels is not None:
        sample_indices = mvf.get_sample_indices(
            labels=args.sample_labels[0].split(","))
    else:
        sample_indices = mvf.get_sample_indices()
    nsamples = len(sample_indices)
    for contig, pos, allelesets in mvf:
        # Check Minimum Site Coverage
        if check_mincoverage(args.mincoverage, allelesets[0]) is False:
            continue
        # Establish first contig
        if current_contig is None:
            current_contig = contig[:]
            if args.windowsize > 0:
                while pos > current_position + args.windowsize - 1:
                    current_position += args.windowsize
        # Check if windows are specified.
        if not same_window((current_contig, current_position),
                           (contig, pos), args.windowsize):
            data[(current_contig, current_position)] = dict([
                ('contig', current_contig),
                ('position', current_position)])
            data[(current_contig, current_position)].update(
                sitepatterns)
            sitepatterns = {}
            if contig != current_contig:
                current_position = 0
                current_contig = contig[:]
            else:
                current_position += (0 if args.windowsize == -1
                                     else args.windowsize)
        if len(allelesets[0]) == 1:
            if allelesets[0] in 'ATGC':
                pattern = 'A' * nsamples
            else:
                continue
        elif allelesets[0][1] == '+':
            continue
        else:
            alleles = mvf.decode(allelesets[0])
            alleles = [alleles[x] for x in sample_indices]
            if any(x in alleles for x in 'X-RYKMWS'):
                continue
            if len(set(alleles)) > 2:
                continue
            pattern = ''.join(['A' if x == alleles[-1] else 'B'
                               for x in alleles[:-1]]) + 'A'
        sitepatterns[pattern] = sitepatterns.get(pattern, 0) + 1
    if sitepatterns:
        data[(current_contig, current_position)] = dict([
            ('contig', current_contig),
            ('position', current_position)])
        data[(current_contig, current_position)].update(
            sitepatterns)
    # WRITE OUTPUT
    headers = ['contig', 'position']
    headers.extend(
        [MLIB.abpattern(x, nsamples)
         for x in range(0, 2 ** nsamples, 2)])
    outfile = OutputFile(path=args.out, headers=headers)
    outfile.write("#{}\n".format(",".join(
        mvf.get_sample_labels(sample_indices))))
    sorted_entries = sorted([(data[k]['contig'],
                              data[k]['position'], k)
                             for k in data])
    for _, _, k in sorted_entries:
        outfile.write_entry(data[k])
    # WRITE LIST OUTPUT
    if args.output_lists is True:
        sorted_entries = sorted([(data[k]['contig'],
                                  data[k]['position'], k)
                                 for k in data])
        total_counts = {}
        for contig, pos, k in sorted_entries:
            outfilepath = "{}-{}-{}.counts.list".format(
                args.out, contig, pos)
            with open(outfilepath, 'w') as outfile:
                outfile.write("pattern,count\n")
                for pattern, pcount in sorted(data[k].items()):
                    if pattern in ['contig', 'position']:
                        continue
                    outfile.write("{},{}\n".format(pattern, pcount))
                    total_counts[pattern] = (
                        total_counts.get(pattern, 0) + pcount)
        outfilepath = "{}-TOTAL.counts.list".format(args.out)
        with open(outfilepath, 'w') as outfile:
            outfile.write("pattern,count\n")
            for pattern, pcount in sorted(total_counts.items()):
                if pattern in ['contig', 'position']:
                    continue
                outfile.write("{},{}\n".format(pattern, pcount))
    return ''


def calc_character_count(args):
    """Count the number of and relative rate of certain bases
       spatially along chromosomes
    """
    mvf = MultiVariantFile(args.mvf, 'read')
    data = {}
    current_contig = None
    current_position = 0
    all_match = 0
    all_total = 0
    data_in_buffer = 0
    # Set up sample indices
    sample_labels = mvf.get_sample_labels()
    if args.sample_indices is not None:
        sample_indices = [int(x) for x in
                          args.sample_indices[0].split(",")]
    elif args.sample_labels is not None:
        sample_indices = mvf.get_sample_indices(
            labels=args.sample_labels[0].split(","))
    else:
        sample_indices = mvf.get_sample_indices()
    # Set up contig ids
    if args.contig_ids is not None:
        contig_ids = args.contig_ids[0].split(",")
    elif args.contig_labels is not None:
        contig_ids = mvf.get_contig_ids(
            labels=args.contig_labels[0].split(","))
    else:
        contig_ids = mvf.get_contig_ids()
    match_counts = dict().fromkeys(
        [sample_labels[i] for i in sample_indices], 0)
    total_counts = dict().fromkeys(
        [sample_labels[i] for i in sample_indices], 0)
    for contig, pos, allelesets in mvf:
        # Check Minimum Site Coverage
        if check_mincoverage(args.mincoverage,
                             allelesets[0]) is False:
            continue
        if contig not in contig_ids:
            continue
        # Establish first contig
        if current_contig is None:
            current_contig = contig[:]
            while pos > current_position + args.windowsize - 1:
                current_position += args.windowsize
        # Check if windows are specified.
        if not same_window((current_contig, current_position),
                           (contig, pos), args.windowsize):
            data[(current_contig, current_position)] = {
                'contig': current_contig, 'position': current_position}
            for k in match_counts:
                data[(current_contig, current_position)].update([
                    (k + '.match', match_counts[k] + all_match),
                    (k + '.total', total_counts[k] + all_total),
                    (k + '.prop', (
                        (float(match_counts[k] + all_match) /
                         float(total_counts[k] + all_total)) if
                        total_counts[k] + all_total > 0 else 0))])
            if contig != current_contig:
                current_contig = contig[:]
                current_position = 0
            else:
                current_position += (0 if args.windowsize == -1
                                     else args.windowsize)
            match_counts = dict().fromkeys(
                [sample_labels[i] for i in sample_indices], 0)
            total_counts = dict().fromkeys(
                [sample_labels[i] for i in sample_indices], 0)
            all_total = 0
            all_match = 0
            data_in_buffer = 0
        else:
            alleles = allelesets[0]
            if len(alleles) == 1:
                if args.base_match is None:
                    all_match += 1
                elif alleles in args.base_match:
                    all_match += 1
                if args.base_total is None:
                    all_total += 1
                elif alleles in args.base_total:
                    all_total += 1
            else:
                alleles = mvf.decode(alleles)
                for i in sample_indices:
                    if args.base_match is None:
                        match_counts[sample_labels[i]] += 1
                    elif alleles[i] in args.base_match:
                        match_counts[sample_labels[i]] += 1
                    if args.base_total is None:
                        total_counts[sample_labels[i]] += 1
                    elif alleles[i] in args.base_total:
                        total_counts[sample_labels[i]] += 1
            data_in_buffer = 1
    if data_in_buffer:
        data[(current_contig, current_position)] = {
            'contig': current_contig, 'position': current_position}
        for k in match_counts:
            data[(current_contig, current_position)].update([
                (k + '.match', match_counts[k] + all_match),
                (k + '.total', total_counts[k] + all_total),
                (k + '.prop', ((float(match_counts[k] + all_match) /
                                float(total_counts[k] + all_total)) if
                               total_counts[k] + all_total > 0 else 0))])
    # WRITE OUTPUT
    headers = ['contig', 'position']
    for label in sample_labels:
        headers.extend([label + x for x in ('.match', '.total', '.prop')])
    outfile = OutputFile(path=args.out,
                         headers=headers)
    sorted_entries = sorted([(data[k]['contig'],
                              data[k]['position'], k)
                             for k in data])
    for _, _, k in sorted_entries:
        outfile.write_entry(data[k])
    return ''


def calc_pairwise_distances(args):
    """Count the pairwise nucleotide distance between
       combinations of samples in a window
    """
    mvf = MultiVariantFile(args.mvf, 'read')
    data = {}
    sample_labels = mvf.get_sample_labels()
    if args.sample_indices is not None:
        sample_indices = [int(x) for x in
                          args.sample_indices[0].split(",")]
    elif args.sample_labels is not None:
        sample_indices = mvf.get_sample_indices(
            labels=args.sample_labels[0].split(","))
    else:
        sample_indices = mvf.get_sample_indices()
    current_contig = None
    current_position = 0
    data_in_buffer = False
    sample_pairs = [tuple(x) for x in combinations(sample_indices, 2)]
    base_matches = dict([(x, {}) for x in sample_pairs])
    all_match = {}
    for contig, pos, allelesets in mvf:
        # Check Minimum Site Coverage
        if check_mincoverage(args.mincoverage, allelesets[0]) is False:
            continue
        # Establish first contig
        if current_contig is None:
            current_contig = contig[:]
            while pos > current_position + args.windowsize - 1:
                current_position += args.windowsize
        # Check if windows are specified.
        if not same_window((current_contig, current_position),
                           (contig, pos), args.windowsize):
            data[(current_contig, current_position)] = {
                'contig': current_contig, 'position': current_position}
            if mvf.flavor == 'dna':
                all_diff, all_total = pairwise_distance_nuc(all_match)
            elif mvf.flavor == 'prot':
                all_diff, all_total = pairwise_distance_prot(all_match)
            for samplepair in base_matches:
                if mvf.flavor == 'dna':
                    ndiff, ntotal = pairwise_distance_nuc(
                        base_matches[samplepair])
                elif mvf.flavor == 'prot':
                    ndiff, ntotal = pairwise_distance_prot(
                        base_matches[samplepair])
                taxa = "{};{}".format(sample_labels[samplepair[0]],
                                      sample_labels[samplepair[1]])
                data[(current_contig, current_position)].update({
                    '{};ndiff'.format(taxa): ndiff + all_diff,
                    '{};ntotal'.format(taxa): ntotal + all_total,
                    '{};dist'.format(taxa): zerodiv(ndiff + all_diff,
                                                    ntotal + all_total)})
            if contig != current_contig:
                current_contig = contig[:]
                current_position = 0
                while pos > current_position + args.windowsize - 1:
                    current_position += args.windowsize
            else:
                current_position += args.windowsize
            base_matches = dict([(x, {}) for x in sample_pairs])
            all_match = {}
            data_in_buffer = False
        alleles = allelesets[0]
        if len(alleles) == 1:
            all_match["{}{}".format(alleles, alleles)] = (
                all_match.get("{}{}".format(alleles, alleles),
                              0) + 1)
            data_in_buffer = True
            continue
        if alleles[1] == '+':
            if 'X' in alleles or '-' in alleles:
                continue
            samplepair = (0, int(alleles[3:]))
            if any(x not in sample_indices for x in samplepair):
                continue
            basepair = "{}{}".format(alleles[0], alleles[2])
            base_matches[samplepair][basepair] = (
                base_matches[samplepair].get(basepair, 0) + 1)
            data_in_buffer = True
            continue
        alleles = mvf.decode(alleles)
        valid_positions = [i for i, x in enumerate(alleles)
                           if x not in 'X-']
        for i, j in combinations(valid_positions, 2):
            samplepair = (i, j)
            if any(x not in sample_indices for x in samplepair):
                continue
            basepair = "{}{}".format(alleles[i], alleles[j])
            base_matches[samplepair][basepair] = (
                base_matches[samplepair].get(basepair, 0) + 1)
        data_in_buffer = True
    if data_in_buffer is True:
        # Check whether, windows, contigs, or total
        if args.windowsize == 0:
            current_contig = 'TOTAL'
            current_position = 0
        elif args.windowsize == -1:
            current_position = 0
        data[(current_contig, current_position)] = {
            'contig': current_contig, 'position': current_position}
        if mvf.flavor == 'dna':
            all_diff, all_total = pairwise_distance_nuc(all_match)
        elif mvf.flavor == 'prot':
            all_diff, all_total = pairwise_distance_prot(all_match)
        for samplepair in base_matches:
            if mvf.flavor == 'dna':
                ndiff, ntotal = pairwise_distance_nuc(base_matches[samplepair])
            elif mvf.flavor == 'prot':
                ndiff, ntotal = pairwise_distance_prot(
                    base_matches[samplepair])
            taxa = "{};{}".format(sample_labels[samplepair[0]],
                                  sample_labels[samplepair[1]])
            data[(current_contig, current_position)].update({
                '{};ndiff'.format(taxa): ndiff + all_diff,
                '{};ntotal'.format(taxa): ntotal + all_total,
                '{};dist'.format(taxa): zerodiv(ndiff + all_diff,
                                                ntotal + all_total)})
    headers = ['contig', 'position']
    for samplepair in sample_pairs:
        headers.extend(['{};{};{}'.format(
            sample_labels[samplepair[0]],
            sample_labels[samplepair[1]],
            x) for x in ('ndiff', 'ntotal', 'dist')])
    outfile = OutputFile(path=args.out, headers=headers)
    sorted_entries = sorted([(
        data[k]['contig'], data[k]['position'], k)
                             for k in data])
    for _, _, k in sorted_entries:
        outfile.write_entry(data[k])
    return ''


def pairwise_distance_nuc(basepairs, strict=False):
    """Calculates pairwise distances between two sequences
        strict = only use ATGC if True,
        choose random heterozygous base if False.
    """
    total = 0
    diff = 0
    for pairbases, paircount in basepairs.items():
        base0, base1 = pairbases[0], pairbases[1]
        if base0 not in MLIB.validchars['dna+ambig'] or (
                base1 not in MLIB.validchars['dna+ambig']):
            continue
        if base0 in MLIB.validchars['dnaambig2']:
            if strict is True:
                continue
            base0 = MLIB.splitbases[base0][randint(0, 1)]
        if base1 in MLIB.validchars['dnaambig2']:
            if strict is True:
                continue
            base1 = MLIB.splitbases[base1][randint(0, 1)]
        if base0 != base1:
            diff += paircount
        total += paircount
    return diff, total


def pairwise_distance_prot(basepairs):
    """Calculates pairwise distances between two sequences
        strict = only use ACDEFGHIKLMNPQRSTVXY if True,
        choose random heterozygous base if False.
    """
    total = 0
    diff = 0
    for pairbases, paircount in basepairs.items():
        base0, base1 = pairbases[0], pairbases[1]
        if base0 not in MLIB.validchars['amino'] or (
                base1 not in MLIB.validchars['amino']):
            continue
        if base0 != base1:
            diff += paircount
        total += paircount
    return diff, total
