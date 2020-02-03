import xml.etree.ElementTree as ET
#from lxml import etree as ET
import base64
import struct
import zlib
import sys
import collections
import operator
import itertools
from bisect import bisect_left
import os
import glob
import concurrent.futures
from multiprocessing import freeze_support
from array import array
#import numpy as np
import time
import cwt
import commonfn

start_time = time.time()

param_set={
        "mzML_files",
        "min_highest_I",
        "num_threads",
        }

param_dict=commonfn.read_param(param_set)

Point=collections.namedtuple('Point',('rt mz I'))

def bin2float(node):
    #if node is None: return ()
    d=base64.b64decode(node.findtext("./{http://psi.hupo.org/ms/mzml}binary"))
    if node.find("*/[@accession='MS:1000574']") is not None:
        d=zlib.decompress(d)
    #fmt='<'+str(int(len(d)/4))+'f' if node.find("*/[@accession='MS:1000523']") is None else '<'+str(int(len(d)/8))+'d'
    fmt='<{}f'.format(int(len(d)/4)) if node.find("*/[@accession='MS:1000523']") is None else '<{}d'.format(int(len(d)/8))
    return struct.unpack(fmt, d)


def store_scan(element):
    rt=element.find(".//*[@accession='MS:1000016']")
    rtinsec=float(rt.get('value'))
    if rt.get('unitName')=="minute":
        rtinsec*=60
    mz=bin2float(element.find(".//*[@accession='MS:1000514'].."))
    inten=bin2float(element.find(".//*[@accession='MS:1000515'].."))
    #return Point(rtinsec,mz,inten)
    return Point(rtinsec,array('d',(m for m,i in zip(mz,inten) if i>0)),array('d',(i for i in inten if i>0)))
    #return Point(rtinsec,np.array([m for m,i in zip(mz,inten) if i>0]),np.array([i for i in inten if i>0]))


mzML_files=sorted(glob.glob(param_dict["mzML_files"]))

num_threads=int(param_dict["num_threads"])


min_group_size=2#int(param_dict["min_group_size"])
min_highest_I=float(param_dict["min_highest_I"])
group_I_threshold=min_highest_I#float(param_dict["group_I_threshold"])
#mz_tol=float(param_dict["mz_width"])/3
mz_space=.015

def print_eic_ms(mzML_file):

    basename0=os.path.basename(mzML_file)
    print(basename0)
    ms1_scans=['MS1']
    ms2_scans=['MS2']

    tree=ET.parse(open(mzML_file,'rb'))

    for element in tree.iter(tag='{http://psi.hupo.org/ms/mzml}spectrum'):
    #for _, element in ET.iterparse(open(mzML_file,'rb')):
        #if element.tag == '{http://psi.hupo.org/ms/mzml}spectrum':
        if element.findtext(".//*{http://psi.hupo.org/ms/mzml}binary"):
            mslevel_elem=element.find("*[@accession='MS:1000511']")
            if mslevel_elem is None:
                ref_id=element.find("{http://psi.hupo.org/ms/mzml}referenceableParamGroupRef").attrib['ref']
                mslevel_elem=(tree.find(".//*{http://psi.hupo.org/ms/mzml}referenceableParamGroup[@id='"+ref_id+"']/*[@accession='MS:1000511']"))
                centroid_elem=(tree.find(".//*{http://psi.hupo.org/ms/mzml}referenceableParamGroup[@id='"+ref_id+"']/*[@accession='MS:1000127']"))
            else:
                centroid_elem=element.find("*[@accession='MS:1000127']")
            if centroid_elem is None:
                print("error: profile mode!")
                sys.exit()
            mslevel=mslevel_elem.attrib['value']
            if mslevel=='1':
                ms1_scans.append(store_scan(element))
            elif mslevel=='2':
                ms2_scans.append((element.find(".//*[@accession='MS:1000744']").get('value'),store_scan(element)))
            else:
                sys.exit()
        element.clear()
        #elif element.tag=='{http://psi.hupo.org/ms/mzml}spectrumList':
        #    break
    del element
    del tree

    print(len(ms1_scans)-1,' MS1 scans')
    print(len(ms2_scans)-1,' MS2 scans')




    #Spec=collections.namedtuple('Spec',('ms1mz rt mz I'))
    #def mz_slice(ms_scans):
    #    all_scans=ms_scans[1:]
    #    ### mz slice
    #    rtdict={rt:n for n,rt in enumerate(sorted({sc.rt for sc in all_scans}))}
    #    data_points=[Point(scan.rt,mz,i) for scan in all_scans for mz,i in zip(scan.mz,scan.I)]
    #    data_points.sort(key=operator.attrgetter('mz'))
    #    EICs=[]
    #    #for sc in sorted(Spec(float(x[0]),x[1].rt,x[1].mz,x[1].I) for x in ms2_scans[1:]):
    #    #    print()
    #    for sc in ms2_scans[1:]:
    #        ms1mz=float(sc[0])
    #        pos0=bisect_left(data_points,ms1mz-mz_tol)
    #        pos1=bisect_left(data_points,ms1mz+mz_tol)
    #        EICs.append(data_points[pos0:pos1])
    #    return ms_scans,EICs

    def mz_slice(ms_scans):
        ### mz slice
        rtdict={rt:n for n,rt in enumerate(sorted({sc.rt for sc in ms_scans[1:]}))}
        ofile.write('scan '+ms_scans[0]+'\n')
        ofile.write('\t'.join([str(x) for x in rtdict.keys()])+'\n')
        data_points=[Point(scan.rt,mz,i) for scan in ms_scans[1:] for mz,i in zip(scan.mz,scan.I)]
        data_points.sort(key=operator.attrgetter('mz'))
        mz_min,mz_max=data_points[0].mz,data_points[-1].mz
        #data_points=np.array([(scan.rt,mz,i) for scan in ms_scans[1:] for mz,i in zip(scan.mz,scan.I)],dtype=[('rt','d'),('mz','d'),('I','d')])
        #data_points=np.sort(data_points,order='mz')
        #mz_min,mz_max=data_points[0]['mz'],data_points[-1]['mz']

        mzlist=array('d',(mz for _,mz,_ in data_points))
        slice_cut=[]
        #mz_max=200
        for i in itertools.takewhile(lambda n:n<mz_max,itertools.count(mz_min,mz_space)):
            pos = bisect_left(mzlist, i)
            slice_cut.append(pos)
        slice_cut.append(len(data_points))
        #for pos,pos1 in zip(slice_cut,slice_cut[3:]):
        for pos,pos1 in zip(slice_cut,slice_cut[2:]):
            dp_sub=data_points[pos:pos1]#.tolist()
            if pos+min_group_size<pos1 and max(I for _,_,I in dp_sub)>min_highest_I:
                eic_dict=dict() # highest intensity in this m/z range
                for rt,mz,I in dp_sub:
                    if rt not in eic_dict or eic_dict[rt][1]<I:
                        eic_dict[rt]=(mz,I)
                if min_group_size<=len({r for r,(_,i) in eic_dict.items() if i>group_I_threshold}):
                    for rt,(mz,i) in sorted(eic_dict.items()):
                        ofile.write('{}\t{}\t{}\n'.format(rt,mz,i))
                    ofile.write('-\n')
        ofile.write('\n')

        #print('len data_points',len(data_points))
        # post processing
        #for eic in EICs[:]:
        #    sorted_rt=sorted({x.rt for x in eic if x.I>group_I_threshold})
        #    del_eic=True
        #    for x,y in zip(sorted_rt,sorted_rt[min_group_size-1:]):
        #        if rtdict[y]-rtdict[x]<min_group_size:
        #        #if rtdict[y]-rtdict[x]==min_group_size-1:
        #            del_eic=False
        #            break
        #    if del_eic:
        #        EICs.remove(eic)
        #print('len EICs',len(EICs),ms_scans[0])
        #return ms_scans,EICs


    with open('eic_'+basename0+'.txt','w') as ofile:
        mz_slice(ms1_scans)


    def print_pt2(ms_scans):
        ofile.write('scan '+ms_scans[0]+'\n')
        for ms1mz,scan_i in ms_scans[1:]:
            ofile.write(ms1mz+'\n')
            ofile.write(str(scan_i.rt)+'\n')
            ofile.write(' '.join(str(x) for x in scan_i.mz)+'\n')
            ofile.write(' '.join(str(x) for x in scan_i.I)+'\n')
        ofile.write('\n')

    if len(ms2_scans)-1:
        with open('ms2spectra_'+basename0+'.txt','w') as ofile:
            print_pt2(ms2_scans)


list(map(print_eic_ms, mzML_files))
if __name__ == '__main__':
    freeze_support()
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_threads) as executor:
        list(executor.map(cwt.cwt, mzML_files))


print("Run time = {:.1f} mins".format(((time.time() - start_time)/60)))


