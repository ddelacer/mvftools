# -*- coding: utf-8 -*-
"""
MVFtools: Multisample Variant Format Toolkit
http://www.github.org/jbpease/mvftools

VCF2MVF: Variant Call Format (VCF) to MVF conversion program
@author: James B. Pease
@author: Ben K. Rosenzweig

Version: 2015-02-01 - First Public Release

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

from __future__ import print_function
import sys, argparse, gzip, os, re
from mvfbase import progress_meter, encode_mvfstring, MultiVariantFile
from mvfbiolib import GTCODES, HAPJOIN

RE_CONTIG_NAME = re.compile("ID=(.*?),")
RE_CONTIG_LENGTH = re.compile("length=(.*?)>")

class VariantCallFile(object):
    """Variant Call Format Handler
    Object Structure:
        path = file path (converted to absolute path)
        metadata = dict of associated data including (but not limited to):
            contigs: dict[id] = dict(metadata)
            samples: dict[index] = dict(sample_info)
    """

    def __init__(self, path, indexcontigs=True):
        if not path:
            raise IOError(path, " path not found for VCF file")
        self.path = os.path.abspath(path)
        self.metadata = {'contigs':{}, 'samples':[]}
        if path.endswith(".gz"):
            filehandler = gzip.open(self.path, 'rb')
        else:
            filehandler = open(self.path, 'rb')
        header_lines = []
        self.entrystart = filehandler.tell()
        line = filehandler.readline()
        while line:
            if line[0] != '#':
                break
            header_lines.append(line.rstrip())
            self.entrystart = filehandler.tell() - 1
            line = filehandler.readline()
        self._process_header(header_lines)
        if not self.metadata['contigs'] and indexcontigs:
            self._index_contigs()


    def _process_header(self, headerlines):
        """Process VCF header information
            Arguments:
                headerlines: list of VCF header strings
        """
        tempid = 0
        for line in headerlines:
            if line[0:12] == '##fileformat':
                self.metadata['sourceformat'] = line[line.find('=') + 1:]
            if line[0:8] == '##contig':
                contig_name = re.findall(RE_CONTIG_NAME, line)
                contig_name = (contig_name and contig_name[0] or (
                    'contig{}'.format(tempid)))
                contig_length = re.findall(RE_CONTIG_LENGTH, line)
                contig_length = contig_length and int(contig_length[0]) or 0
                self.metadata['contigs'][tempid] = {
                    'label':contig_name, 'length': contig_length}
                tempid += 1
            elif line[0:6] == '#CHROM':
                self.metadata['samples'] = [
                    '/' in elem and elem[elem.rfind('/') + 1:] or elem
                    for elem in line.split()[9:]]
        return ''

    def _index_contigs(self, fieldsep="\t"):
        """Go through entries and index contig names
            Arguments:
                fielsep: separator for fields in VCF file
        """
        tempid = 0
        contigndx = {}
        if self.path.endswith('.gz'):
            filehandler = gzip.open(self.path, 'rb')
        else:
            filehandler = open(self.path, 'rb')
        filehandler.seek(self.entrystart)
        for vcfline in filehandler:
            try:
                arr = vcfline.rstrip().split(fieldsep)
                contig = arr[0]
                coord = int(arr[1])
                if contig not in contigndx:
                    self.metadata['contigs'][tempid] = {
                        'label': contig, 'length': coord}
                    contigndx[contig] = tempid
                    tempid += 1
                else:
                    self.metadata['contigs'][contigndx[contig]]['length'] = (
                        max(self.metadata['contigs'][
                            contigndx[contig]]['length'],
                            coord))
            except:
                continue
        return ''

    def iterentries(self, args):
        """Iterate VCF data entries
            Arguments:
                args: dict passthrough object from toplevel argparse options
        """
        quiet = args['quiet']
        if self.path.endswith('.gz'):
            filehandler = gzip.open(self.path, 'rb')
        else:
            filehandler = open(self.path, 'rb')
        if not quiet:
            filesize = os.stat(self.path).st_size
            progress_meter(0, filesize)
        nline = 0
        filehandler.seek(self.entrystart)
        linebuffer = []
        for line in filehandler:
            nline += 1
            linebuffer.append(line)
            if nline == args['linebuffer']:
                if not quiet:
                    progress_meter(filehandler.tell(), filesize)
                for line in linebuffer:
                    vcfrecord = self._parse_entry(line, **args)
                    if vcfrecord == -1:
                        continue
                    yield vcfrecord
                linebuffer = []
                nline = 0
        for line in linebuffer:
            vcfrecord = self._parse_entry(line, **args)
            if vcfrecord == -1:
                continue
            yield vcfrecord
            linebuffer = []
            nline = 0
        filehandler.close()

    def _parse_entry(self, vcfline, **kwargs):
        """Reads and processes a VCF multi-sample record
            Arguments:
                vcfile: string from VCF data entry
                **kwargs: passthrough dict of arguments
        """
        record = {}
        ## Skip indels and zero-depth
        if any((x in vcfline for x in ['INDEL', 'DP=0'])):
            return -1
        arr = vcfline.rstrip().split(kwargs.get('fieldsep', '\t'))
        if len(arr) < 9:
            return -1
        if len(arr[3]) > 1:
            return -1
        record['contig'] = arr[0]
        record['coord'] = int(arr[1])
        record['alleles'] = [arr[3]]
        if arr[4] != '.':
            for altbase in arr[4].split(','):
                if len(altbase) > 1:
                    return -1
                record['alleles'].append(altbase)
        record['tagindex'] = {}
        tags = arr[8].split(':')
        for tag in ["DP", "PL", "GT", "GL", "GQ"]:
            if tag in tags:
                record['tagindex'][tag] = tags.index(tag)
            else:
                record['tagindex'][tag] = -1
        record['samples'] = arr[9:]
        record['genotypes'] = [record['alleles'][0]]
        for j in xrange(len(record['samples'])):
            record['genotypes'].append(
                self._call_allele(record['samples'][j].split(':'),
                                  record['alleles'], record['tagindex'],
                                  **kwargs))
        if kwargs.get("allelesfrom"):
            info = dict(field.split('=') for field in arr[7].split(';'))
            record['genotypes'].extend(
                info.get(label, '-') for label in kwargs.get("allelesfrom"))
        return record

    def _call_allele(self, sample, alleles, indices, **kwargs):
        """Determine the allele from a VCF entry
            Arguments:
                sample: list of entry string elements
                alleles: alleles for all samples across lines
                indices: locations in each sample string of information fields
                **kwargs: passthrough arguments
        """
        if sample[0] == './.':
            return '-'
        try:
            sample_depth = int(sample[indices['DP']])
        except:
            sample_depth = -1
        ## No coverage
        if sample_depth == 0:
            return '-'
        ## Fixed sites
        if all(((indices[x] == -1 or sample[indices[x]] == '.')
                for x in ('PL', 'GL', 'GQ'))):
            if sample[indices['GT']] == '0/0':
                res = (alleles[0], 60)
            elif sample[indices['GT']] == '1/1':
                res = (alleles[1], 60)
            elif sample[indices['GT']] == '0/1':
                res = (HAPJOIN[''.join(alleles[0:2])], 60)
            else:
                res = ('X', 60)
        ## Low coverage
        elif -1 < sample_depth < kwargs.get("maskdepth", 1):
            return 'X'
        ## Invariant sites
        elif len(alleles) == 1:
            try:
                if indices["PL"] == -1:
                    res = (alleles[0], 60)
                elif indices["PL"] == -1 and indices["GL"] > -1:
                    try:
                        res = (alleles[0], int(sample[indices["GL"]]))
                    except:
                        res = (alleles[0], 3)
                elif indices["PL"] == '.' and indices["GL"] == -1:
                    try:
                        res = (alleles[0], int(sample[indices["GQ"]]))
                    except:
                        res = (alleles[0], 3)
                else:
                    res = (alleles[0], int(sample[indices['PL']]))
            except:
                return 'X'
        ## Variant site
        elif len(alleles) <= 4:
            try:
                if indices['PL'] == -1 and indices['GL'] != -1:
                    plvalues = [int(x)
                                for x in sample[indices['GL']].split(',')]
                else:
                    plvalues = [int(x)
                                for x in sample[indices['PL']].split(',')]
                maxpl = 0 not in plvalues and max(plvalues) or 0
                imaxpl = (plvalues.count(maxpl) != 1
                          and -1 or plvalues.index(maxpl))
                res = (imaxpl == -1 and ('X', maxpl) or (
                    HAPJOIN[''.join([alleles[x]
                                     for x in GTCODES[imaxpl]])], maxpl))
            except:
                return 'X'
        ## Error checking (you should never see a ! in the MVF)
        else:
            res = ('!', 0)
        sample_allele = res[0]
        ## Lower-case mask for low Quality or Depth,
        ## Change to X for very low Quality or Depth
        if res[1] == 0:
            if -1 < sample_depth < kwargs.get("lowdepth", 3):
                sample_allele = sample_allele.lower()
        elif res[1] < kwargs.get("maskqual", 20):
            sample_allele = 'X'
        elif (res[1] < kwargs.get("lowqual", 20)
              or -1 < sample_depth < kwargs.get("lowdepth", 3)):
            sample_allele = sample_allele.lower()
        return sample_allele

def main(arguments=sys.argv[1:]):
    """Main method for vcf2mvf"""
    parser = argparse.ArgumentParser(description="""
    Converts multisample-VCF to MVF file with filtering """)
    parser.add_argument("--vcf", help="input VCF file", required=True)
    parser.add_argument("--out", help="output MVF file", required=True)
    parser.add_argument("--maskdepth", type=int, default=1,
                        help="below this depth mask with N/n")
    parser.add_argument("--lowdepth", type=int, default=3,
                        help="""below this depth convert to lower case
                              set to 0 to disable""")
    parser.add_argument("--maskqual", type=int, default=3,
                        help="""low quality cutoff, bases replaced by N/-
                             set to 0 to disable""")
    parser.add_argument("--lowqual", type=int, default=20,
                        help="""below this quality convert to lower case
                                set to 0 to disable""")
    parser.add_argument("--contigids", nargs='*',
                        help=("""manually specify one or more contig ids
                                 as ID:NAME"""))
    parser.add_argument("--samplereplace", nargs="*",
                        help="""one or more TAG:NEWLABEL or TAG, items,
                                if TAG found in sample label, replace with
                                NEW (or TAG if NEW not specified)
                                NEW and TAG must each be unique""")
    parser.add_argument("--reflabel", default="REF",
                        help="label for reference sample (default='REF')")
    parser.add_argument("--allelesfrom", default=None,
                        help="""get additional alignment columns
                                from INFO fields (:-separated)""")
    parser.add_argument("--linebuffer", type=int, default=100000,
                        help="number of lines to hold in read/write buffer")
    parser.add_argument("--no_autoindex", action="store_true",
                        help="do not automatically index contigs from the VCF")
    parser.add_argument("--fieldsep", default="TAB",
                        choices=['TAB', 'SPACE', 'DBLSPACE', 'COMMA', 'MIXED'],
                        help="""VCF field separator (default='TAB')""")
    parser.add_argument("--overwrite", action="store_true",
                        help="USE WITH CAUTION: force overwrite of outputs")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress progress meter")
    parser.add_argument("-v", "--version", action="store_true",
                        help="display version information")
    args = parser.parse_args(args=arguments)
    if args.version:
        print("Version 2015-02-01: Initial Public Release")
        sys.exit()
    sepchars = dict([("TAB", "\t"), ("SPACE", " "), ("DBLSPACE", "  "),
                     ("COMMA", ","), ("MIXED", None)])
    args.fieldsep = sepchars[args.fieldsep]
    ## ESTABLISH VCF
    vcf = VariantCallFile(args.vcf, indexcontigs=(not args.no_autoindex))
    ## ESTABLISH MVF
    mvf = MultiVariantFile(args.out, 'write', overwrite=args.overwrite)
    # PROCESS CONTIG INFO
    contigs = vcf.metadata['contigs'].copy()
    maxcontigid = 0
    newids = set([])
    if args.contigids:
        for cid, cname in (x.split(':') for x in args.contigids):
            for tempid in contigs:
                if cname in contigs[tempid]['label']:
                    try:
                        cid = int(cid)
                    except ValueError:
                        pass
                    mvf.metadata['contigs'][cid] = contigs[tempid].copy()
                    del contigs[tempid]
                    newids.update([cid])
                    break
        for cid in newids:
            try:
                maxcontigid = max([maxcontigid, int(cid) + 1])
            except ValueError:
                continue
    tempids = set(contigs.keys()) - newids
    for tempid, newid in sorted(zip(
            tempids, xrange(maxcontigid, maxcontigid + len(tempids)))):
        mvf.metadata['contigs'][newid] = vcf.metadata['contigs'][tempid]
    contig_translate = dict([(mvf.metadata['contigs'][x]['label'], x)
                             for x in mvf.metadata['contigs']])
    # PROCESS SAMPLE INFO
    samplelabels = [args.reflabel] + vcf.metadata['samples'][:]
    if args.allelesfrom:
        args.allelesfrom = args.allelesfrom.split(':')
        samplelabels += args.allelesfrom
    if args.samplereplace:
        newsample = [':' in tuple(x) and x.split(':') or tuple([x, x])
                     for x in args.samplereplace]
        unmatched = [x for x in enumerate(samplelabels)]
        for old, new in newsample:
            labelmatched = False
            for j, (i, name) in enumerate(unmatched):
                if old in name:
                    samplelabels[i] = new
                    labelmatched = j
                    break
            if labelmatched != False:
                del unmatched[labelmatched]
    mvf.metadata['labels'] = samplelabels[:]
    for i, label in enumerate(samplelabels):
        mvf.metadata['samples'][i] = {'label': label}
    mvf.metadata['ncol'] = len(mvf.metadata['labels'])
    mvf.metadata['sourceformat'] = vcf.metadata['sourceformat']
    ## WRITE MVF HEADER
    mvf.write_data(mvf.get_header())
    mvfentries = []
    nentry = 0
    for vcfrecord in vcf.iterentries(vars(args)):
        mvf_alleles = encode_mvfstring(''.join(vcfrecord['genotypes']))
        if mvf_alleles:
            mvfentries.append(
                (contig_translate.get(vcfrecord['contig'], vcfrecord['contig']),
                 vcfrecord['coord'], mvf_alleles))
            nentry += 1
            if nentry == args.linebuffer:
                mvf.write_entries(mvfentries, encoded=True)
                mvfentries = []
                nentry = 0
    if mvfentries:
        mvf.write_entries(mvfentries)
        mvfentries = []
    return ''


if __name__ == "__main__":
    main()