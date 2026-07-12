import sys, types
for _m in ["pyam"]: sys.modules[_m]=types.ModuleType(_m)
import warnings; warnings.filterwarnings('ignore')
import numpy as np, torch, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from gpytorch import kernels
from linear_operator.operators import LinearOperator
if not hasattr(LinearOperator,'evaluate'): LinearOperator.evaluate=LinearOperator.to_dense
from src.preprocessing.glob import make_data
from src.models.utils import compute_means, compute_I, compute_covariance
torch.set_default_dtype(torch.float64)

cfg={'dataset':{'dirpath':'data/','keys':['historical','ssp245']}}
data=make_data(cfg); ds=data.scenarios
q=torch.from_numpy(data.fair_kwargs['q']).double(); d=torch.from_numpy(data.fair_kwargs['d']).double()
years=ds.timesteps.numpy().astype(int); nhist=int((years<=2014).sum())
ssp=years[nhist:]; i2050=int(np.where(ssp==2050)[0][0]); i2025=int(np.where(ssp==2025)[0][0])
means=compute_means(ds); m=torch.cat([v for v in means.values()]).sum(-1).double(); y=ds.tas.double(); r=y-m
def iv_cov(size,s2):
    idx=torch.arange(size).double(); dist=(idx.view(-1,1)-idx.view(1,-1)).abs()
    return s2*(0.5*(q/d)**2*torch.exp(-dist.unsqueeze(-1)/d)).sum(-1)
def Kphys(kernel): I=compute_I(ds,kernel,q,d); return compute_covariance(ds,I,q,d).double()
kernel=kernels.ScaleKernel(kernels.MaternKernel(nu=1.5,ard_num_dims=4,active_dims=[1,2,3,4])).double()
log_s2=torch.tensor(np.log(0.05),requires_grad=True)
opt=torch.optim.Adam(list(kernel.parameters())+[log_s2],lr=0.05); rh=r[:nhist]
for it in range(120):
    opt.zero_grad(); K=Kphys(kernel)
    Krr=K[:nhist,:nhist]+iv_cov(nhist,log_s2.exp())+1e-5*torch.eye(nhist)
    L=torch.linalg.cholesky(Krr); a=torch.cholesky_solve(rh.unsqueeze(-1),L)
    nll=0.5*(rh@a.squeeze()+2*torch.log(torch.diag(L)).sum()); nll.backward(); opt.step()
with torch.no_grad(): K=Kphys(kernel).detach(); s2=log_s2.exp().detach()
print('fitted outputscale',float(kernel.outputscale),'iv s2',float(s2),
      'lengthscales',np.round(kernel.base_kernel.lengthscale.detach().numpy().ravel(),2))

def post(train_idx, ivsizes):
    tr=train_idx; Krr=K[np.ix_(tr,tr)].clone(); off=0
    for sz in ivsizes: Krr[off:off+sz,off:off+sz]+=iv_cov(sz,s2); off+=sz
    Krr+=1e-6*torch.eye(len(tr)); L=torch.linalg.cholesky(Krr)
    Ktt=K[nhist:,nhist:]; Ktr=K[np.ix_(range(nhist,len(years)),tr)]
    mean=m[nhist:]+(Ktr@torch.cholesky_solve(r[tr].unsqueeze(-1),L)).squeeze()
    var=(Ktt-Ktr@torch.cholesky_solve(Ktr.T,L)).diagonal().clamp(min=1e-9)
    return mean.numpy(), var.numpy()
mA,vA=post(list(range(nhist)),[nhist])
mB,vB=post(list(range(nhist))+list(range(nhist,nhist+i2025+1)),[nhist,i2025+1])
sk=np.sqrt(np.mean((mA-y[nhist:].numpy())**2)); print('FaIRGP hist-only SSP245 GMST RMSE=%.3fK (sanity)'%sk)
print('FaIRGP var(2050): hist=%.4f hist+test=%.4f  reduction=%.1f%%'%(vA[i2050],vB[i2050],100*(1-vB[i2050]/vA[i2050])))

# plain GP
mu=ds.inputs.double().mean(0); sig=ds.inputs.double().std(0).clamp(min=1e-6)
Xe=((ds.inputs.double()-mu)/sig)[:,1:5]
pk=kernels.ScaleKernel(kernels.MaternKernel(nu=1.5,ard_num_dims=4)).double(); pln=torch.tensor(np.log(0.05),requires_grad=True)
po=torch.optim.Adam(list(pk.parameters())+[pln],lr=0.05)
for it in range(150):
    po.zero_grad(); Kp=pk(Xe[:nhist]).evaluate()+(pln.exp()+1e-5)*torch.eye(nhist)
    L=torch.linalg.cholesky(Kp); a=torch.cholesky_solve(y[:nhist].unsqueeze(-1),L)
    nll=0.5*(y[:nhist]@a.squeeze()+2*torch.log(torch.diag(L)).sum()); nll.backward(); po.step()
with torch.no_grad(): Kpf=pk(Xe).evaluate().double(); pn=pln.exp().detach()
def ppost(tr):
    Krr=Kpf[np.ix_(tr,tr)]+(pn+1e-5)*torch.eye(len(tr)); L=torch.linalg.cholesky(Krr)
    Ktt=Kpf[nhist:,nhist:]; Ktr=Kpf[np.ix_(range(nhist,len(years)),tr)]
    return (Ktt-Ktr@torch.cholesky_solve(Ktr.T,L)).diagonal().clamp(min=1e-9).numpy()
pvA=ppost(list(range(nhist))); pvB=ppost(list(range(nhist))+list(range(nhist,nhist+i2025+1)))
print('PlainGP var(2050): hist=%.4f hist+test=%.4f reduction=%.1f%%'%(pvA[i2050],pvB[i2050],100*(1-pvB[i2050]/pvA[i2050])))

# ---- figure ----
ACC='#2166ac'; ACC2='#b2182b'; G='#555'
fig,ax=plt.subplots(1,2,figsize=(9.8,4.2))
ax[0].plot(ssp,y[nhist:].numpy(),color=G,lw=1,label='NorESM2 (truth)',zorder=5)
ax[0].fill_between(ssp,mA-2*np.sqrt(vA),mA+2*np.sqrt(vA),color=ACC,alpha=.18,label='trained to 2014')
ax[0].fill_between(ssp,mB-2*np.sqrt(vB),mB+2*np.sqrt(vB),color=ACC2,alpha=.25,label='+ 2015–2025 test window')
ax[0].plot(ssp,mA,color=ACC,lw=1.2); ax[0].axvline(2050,color='k',lw=.7,ls=':')
ax[0].set_xlim(2015,2100); ax[0].set_xlabel('Year'); ax[0].set_ylabel('GMST anomaly (K)')
ax[0].set_title('(a) FaIRGP 2050 projection posterior',fontsize=10,loc='left'); ax[0].legend(fontsize=7,loc='upper left')
for s in['top','right']: ax[0].spines[s].set_visible(False)
redF=100*(1-vB/vA); redP=100*(1-pvB/pvA)
ax[1].plot(ssp,redF,color=ACC2,lw=1.8,label='FaIRGP (physical prior)')
ax[1].plot(ssp,redP,color=G,lw=1.5,ls='--',label='plain GP (physics-free)')
ax[1].axvline(2050,color='k',lw=.7,ls=':'); ax[1].axhline(0,color='k',lw=.5)
ax[1].set_xlim(2026,2100); ax[1].set_xlabel('Projection horizon (year)')
ax[1].set_ylabel('2050-target variance reduction from\nthe 2015–2025 window (%)')
ax[1].set_title('(b) Information the test window carries forward',fontsize=10,loc='left'); ax[1].legend(fontsize=7)
for s in['top','right']: ax[1].spines[s].set_visible(False)
fig.tight_layout(); fig.savefig('faistgp_testwindow.png',dpi=200,bbox_inches='tight'); fig.savefig('faistgp_testwindow.pdf',bbox_inches='tight')
np.savez('faistgp_results.npz',ssp=ssp,y=y[nhist:].numpy(),mA=mA,mB=mB,vA=vA,vB=vB,pvA=pvA,pvB=pvB,i2050=i2050)
print('saved figure')
