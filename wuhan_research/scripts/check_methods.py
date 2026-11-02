"""Independent small exact-enumeration checks of inference and allocation."""
import itertools,json
from pathlib import Path
import numpy as np
from scipy import sparse
from run_analysis import local_mc,queen,overlap

root=Path(__file__).resolve().parents[1]
x=np.array([[1.,9.,2.],[2.,7.,3.],[8.,1.,10.],[3.,6.,5.],[9.,2.,9.],[6.,3.,8.]])
z=(x-x.mean(0))/x.std(0)
A=queen(2,3,np.arange(6));o=local_mc(x,z,A.indptr,A.indices,9999,77)
reports=[]
for i in [0,2,3,5]:
 k=int(A[i].sum());ns=A[i].indices
 assert i not in ns and k==3
 for h in range(3):
  comb=list(itertools.combinations([j for j in range(6) if j!=i],k))
  simI=np.array([z[i,h]*z[list(c),h].mean() for c in comb])
  simS=np.array([x[i,h]+x[list(c),h].sum() for c in comb])
  obsI=z[i,h]*z[ns,h].mean();obsS=x[i,h]+x[ns,h].sum()
  ei=-z[i,h]**2/5;eg=x[i,h]+k*(x[:,h].sum()-x[i,h])/5
  pi=np.mean(abs(simI-ei)>=abs(obsI-ei)-1e-12);pg=np.mean(abs(simS-eg)>=abs(obsS-eg)-1e-10)
  assert abs(o[i,h,4]-pi)<.035 and abs(o[i,h,5]-pg)<.035
  assert abs(o[i,h,2]-obsS/x[:,h].sum())<1e-12
  assert abs(o[i,h,3]-(obsS-simS.mean())/simS.std())<1e-10
  reports.append(dict(unit=i,indicator=h,exact_lisa_p=pi,mc_lisa_p=o[i,h,4],exact_gistar_p=pg,mc_gistar_p=o[i,h,5]))
# Pixel boundaries at 15 m, cell boundary at 20 m => 2nd pixel splits 5/10 m.
ox=overlap(3,15,20).toarray();assert np.array_equal(ox,np.array([[15,5,0],[0,10,10],[0,0,5]]))
assert np.array_equal(ox.sum(0),np.full(3,15))
out={'queen_binary_diagonal_zero':bool(np.all(A.diagonal()==0)),'Gistar_self_once':True,'conditional_null_exact_enumeration_checks':reports,'pixel_overlap_15m_20m_exact':ox.tolist(),'status':'PASS'}
(root/'qa/small_method_checks.json').write_text(json.dumps(out,indent=2))
print('PASS: conditional permutation vs exhaustive enumeration; Queen/self weights; exact boundary pixel splits')
