"""
ClimateBench v2 demonstration: information in the 2015-2025 test window about the
2050 GMST change, under joint uncertainty in climate sensitivity (scaled equilibrium
response, ECS = s * ECS0) and aerosol forcing amplitude (alpha, normalized so alpha=1
gives -1.0 W/m2 aerosol ERF over 2005-2014; time-shape from FaIR/ClimateBench emissions).
Grid-posterior (Bayesian) version of the frequentist subsampling in Watson-Parris
(GRL, 2025). Truth: NorESM2-LM (ClimateBench v1.0), historical + ssp245.
Caveats: sensitivity scaling keeps response timescales fixed; statistics treated as
independent Gaussians with AR(1)-corrected internal-variability sds; no volcanic forcing
in the FaIR mean (present in NorESM2); single-realization 'observations'.
"""
import sys, types
for _m in ["pyam"]: sys.modules[_m]=types.ModuleType(_m)
import warnings; warnings.filterwarnings('ignore')
import numpy as np, xarray as xr, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from src.preprocessing.glob import make_data
import src.fair as fair

cfg={'dataset':{'dirpath':'data/','keys':['historical','ssp245']}}
data=make_data(cfg); scn=data.scenarios['ssp245']
tfull=scn.full_timesteps.numpy(); years=tfull.astype(int)
res=fair.run(tfull, scn.full_emissions.T.numpy(), fair.get_params())
F_ghg=res['RF'][:2].sum(0); F_aer=res['RF'][2:].sum(0)
F_aer=F_aer*(-1.0/F_aer[(years>=2005)&(years<=2014)].mean())      # AR6-central amplitude at alpha=1
q=data.fair_kwargs['q']; d=data.fair_kwargs['d']; ECS0=3.93*q.sum()

def impulse_response(F):
    dec=np.exp(-1.0/d); S=np.zeros((len(F),len(d)))
    for t in range(1,len(F)): S[t]=S[t-1]*dec+q*F[t]*(1-dec)
    return S.sum(1)
T_G=impulse_response(F_ghg); T_A=impulse_response(F_aer)
def mean_win(y,yy,a,b): m=(yy>=a)&(yy<=b); return y[m].mean()
def ols_trend(y,yy,a,b):
    m=(yy>=a)&(yy<=b); t=yy[m]-yy[m].mean(); return 10*np.sum(t*y[m])/np.sum(t*t)
base=lambda y,yy: y-mean_win(y,yy,1850,1900)
tG,tA=base(T_G,years),base(T_A,years)
SPEC={'L':((1995,2014),'mean'),'t40':((1975,2014),'trend'),
      'L11':((2015,2025),'mean'),'t11':((2015,2025),'trend'),
      'D50':((2041,2050),'mean'),'Dbase':((1990,2020),'mean')}
GA={k:((mean_win(tG,years,*w) if f=='mean' else ols_trend(tG,years,*w)),
       (mean_win(tA,years,*w) if f=='mean' else ols_trend(tA,years,*w))) for k,(w,f) in SPEC.items()}

oh=xr.open_dataset('data/outputs_historical.nc'); os_=xr.open_dataset('data/outputs_ssp245.nc')
w=np.cos(np.deg2rad(oh.lat))
g=xr.concat([oh.tas.weighted(w).mean(['lat','lon']), os_.tas.weighted(w).mean(['lat','lon'])],dim='time')
gy=g.time.values.astype(int); g=g-g.sel(time=slice(1850,1900)).mean('time')
gm=g.mean('member').values
resid=(g-g.mean('member')).values
sig=np.sqrt(np.var(resid)*1.5); rho=np.corrcoef(resid[:,:-1].ravel(),resid[:,1:].ravel())[0,1]
ar1=np.sqrt((1+rho)/(1-rho))
def sd_trend(n): t=np.arange(n)-(n-1)/2.; return 10*sig/np.sqrt((t*t).sum())*ar1
def sd_mean(n): return sig*ar1/np.sqrt(n)
SD={'L':sd_mean(20),'t40':sd_trend(40),'L11':sd_mean(11),'t11':sd_trend(11)}
truth_D50=mean_win(gm,gy,2041,2050)-mean_win(gm,gy,1990,2020)

s_grid=np.linspace(0.4,2.8,481); a_grid=np.linspace(0.0,2.5,401)
S,A=np.meshgrid(s_grid,a_grid,indexing='ij'); ECS=S*ECS0; AER=-1.0*A
st=lambda k: S*(GA[k][0]+A*GA[k][1])
D50=st('D50')-st('Dbase')
def posterior(o,names):
    ll=sum(-0.5*((st(n)-o[n])/SD[n])**2 for n in names)
    p=np.exp(ll-ll.max()); return p/p.sum()
def qtl(p,val,qs):
    v=val.ravel(); i=np.argsort(v); c=np.cumsum(p.ravel()[i]); c/=c[-1]; return np.interp(qs,c,v[i])
def summarize(p,val):
    mu=np.sum(p*val); return qtl(p,val,[.05,.5,.95]), np.sqrt(np.sum(p*(val-mu)**2))

print('IV sig=%.3f rho=%.2f; sds:'%(sig,rho),{k:round(v,3) for k,v in SD.items()})
print('unit-s (GHG,aer):',{k:(round(v[0],3),round(v[1],3)) for k,v in GA.items()})
keep={}
for m in range(3):
    obs=g.isel(member=m).values
    o={k:(mean_win(obs,gy,*w_) if f=='mean' else ols_trend(obs,gy,*w_)) for k,(w_,f) in SPEC.items() if 'D' not in k}
    pA=posterior(o,['L','t40']); pB=posterior(o,['L','t40','L11','t11'])
    (qa,sa),(qb,sb)=summarize(pA,D50),summarize(pB,D50)
    (ea,_),(eb,_)=summarize(pA,ECS),summarize(pB,ECS)
    red=100*(1-sb**2/sa**2)
    # attribution: window trend only / level only
    _,s_t=summarize(posterior(o,['L','t40','t11']),D50); _,s_l=summarize(posterior(o,['L','t40','L11']),D50)
    print(f'member{m}: t11={o["t11"]:+.3f} | D50 A:{qa[1]:.2f}[{qa[0]:.2f},{qa[2]:.2f}] '
          f'B:{qb[1]:.2f}[{qb[0]:.2f},{qb[2]:.2f}] varred {red:.0f}% (trend-only {100*(1-s_t**2/sa**2):.0f}%, level-only {100*(1-s_l**2/sa**2):.0f}%) '
          f'| ECS A:{ea[1]:.2f}[{ea[0]:.2f},{ea[2]:.2f}] B:{eb[1]:.2f}[{eb[0]:.2f},{eb[2]:.2f}]')
    keep[m]=(o,pA,pB,qa,qb,red)
print('truth D50=%.2fK'%truth_D50)

# ---------- figure (member 1 = median-behaved; range cited in caption) ----------
mm=0
o,pA,pB,qa,qb,red=keep[mm]
ACC='#2166ac'; ACC2='#b2182b'; G='#555'
fig,ax=plt.subplots(1,2,figsize=(9.8,4.2))
def contour(p,color,label):
    ps=np.sort(p.ravel())[::-1]; c=np.cumsum(ps)
    lev=[ps[np.searchsorted(c,f)] for f in (0.9,0.5)]
    ax[0].contour(ECS,AER,p,levels=sorted(lev),colors=color,linewidths=[1.0,1.8])
    ax[0].plot([],[],color=color,label=label)
contour(pA,ACC,'trained to 2014')
contour(pB,ACC2,'+ 2015–2025 window')
ax[0].axvline(2.54,color=G,lw=.8,ls=':'); ax[0].annotate(' NorESM2 ECS',(2.54,-2.4),fontsize=7,color=G)
ax[0].set_xlabel('ECS (K)'); ax[0].set_ylabel('Aerosol ERF, 2005–2014 (W m$^{-2}$)')
ax[0].set_xlim(1,6.4); ax[0].set_ylim(-2.5,0)
ax[0].set_title('(a) Joint posterior (50%, 90% credible)',fontsize=10,loc='left'); ax[0].legend(fontsize=7,loc='lower right')
for sp in['top','right']: ax[0].spines[sp].set_visible(False)
edges=np.linspace(0,2.0,201); cent=0.5*(edges[1:]+edges[:-1])
def hist(p): h,_=np.histogram(D50.ravel(),bins=edges,weights=p.ravel()); return h/np.trapz(h,cent)
ax[1].fill_between(cent,hist(pA),color=ACC,alpha=.25); ax[1].plot(cent,hist(pA),color=ACC,lw=1.4,label=f'to 2014: [{qa[0]:.2f}, {qa[2]:.2f}] K')
ax[1].fill_between(cent,hist(pB),color=ACC2,alpha=.25); ax[1].plot(cent,hist(pB),color=ACC2,lw=1.6,label=f'+ window: [{qb[0]:.2f}, {qb[2]:.2f}] K')
ax[1].axvline(truth_D50,color='k',lw=1.2,ls='--',label='NorESM2 forced truth')
ax[1].set_xlabel('2050 change: T(2041–2050) − T(1990–2020)  (K)')
ax[1].set_ylabel('Posterior density'); ax[1].set_xlim(0,2.0)
ax[1].set_title(f'(b) 2050-change posterior ({red:.0f}% variance reduction)',fontsize=10,loc='left')
ax[1].legend(fontsize=7)
for sp in['top','right']: ax[1].spines[sp].set_visible(False)
fig.tight_layout(); fig.savefig('sens_testwindow.png',dpi=200,bbox_inches='tight'); fig.savefig('sens_testwindow.pdf',bbox_inches='tight')
np.savez('sens_results.npz',ECS=ECS,AER=AER,D50=D50,truth=truth_D50,
         **{f'p{ab}{m}':keep[m][1 if ab=='A' else 2] for m in range(3) for ab in 'AB'})
print('saved figure + results')
