"""
Tier III motivation figure: paleo GMST anomaly vs CO2 radiative forcing.
Proxy assessments (large markers, error bars) + model ensembles (small dots)
from the IPCC AR6 Ch.7 Fig 7.19 archived data (Lunt, 2023; CEDA
doi:10.5285/9ce84c3a242e4b999c24dc1647c89794). LIG point: Fischer et al. (2018);
MH point: Kaufman et al. (2020) [VALUES TO VERIFY]. CO2 ERF = 5.35 ln(C/284).
"""
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt

mod=pd.read_csv('Figure7_19_mod.csv',skiprows=2)
mod.columns=['period','model','dT','ecs_flag']
obs=pd.read_csv('Figure7_19_obs.csv',skiprows=2)
obs.columns=['period','tmin','tmean','tmax']
F=lambda c: 5.35*np.log(c/284.0)

# period: (CO2 central, lo, hi, color, in-protocol?)
P={'LGM' :(190,180,200,'#2166ac',True),
   'MPWP':(400,350,450,'#e6a817',False),
   'EECO':(1470,1150,2500,'#b2182b',False)}
extra={'MH' :(264,260,268,'#008080',True,0.6,0.2,1.0),   # Kaufman et al. 2020 (VERIFY)
       'LIG':(275,270,280,'#7b3294',True,0.5,0.0,1.0)}   # Fischer et al. 2018 (+0.5 [0,1])

fig,ax=plt.subplots(figsize=(6.4,5.0))
# ESS guide lines (K per W/m2) through PI
xx=np.linspace(-3.2,13,10)
for s,lab,lx in [(0.5,'0.5',12.6),(1.0,'1',12.6),(2.0,'2',9.2)]:
    ax.plot(xx,s*xx,color='0.85',lw=0.8,zorder=0)
    ax.annotate(f'{lab} K (W m$^{{-2}}$)$^{{-1}}$',(lx,s*lx),fontsize=6,color='0.6',
                ha='right',va='bottom')
rng=np.random.default_rng(42)
for per,(c,lo,hi,col,in_proto) in P.items():
    x0=F(c)
    m=mod[mod.period==per]
    ax.scatter(x0+rng.normal(0,0.06,len(m)),m.dT,s=13,color=col,alpha=.55,lw=0,zorder=3)
    o=obs[obs.period==per].iloc[0]
    face=col if in_proto else 'white'
    ax.errorbar(x0,o.tmean,yerr=[[o.tmean-o.tmin],[o.tmax-o.tmean]],
                xerr=[[x0-F(lo)],[F(hi)-x0]],fmt='o',ms=11,mfc=face,mec=col,mew=1.8,
                ecolor=col,elinewidth=1.2,capsize=0,zorder=4)
for per,(c,lo,hi,col,in_proto,tm,tlo,thi) in extra.items():
    x0=F(c)
    ax.errorbar(x0,tm,yerr=[[tm-tlo],[thi-tm]],xerr=[[x0-F(lo)],[F(hi)-x0]],
                fmt='o',ms=11,mfc=col,mec=col,mew=1.8,ecolor=col,elinewidth=1.2,capsize=0,zorder=4)
ax.scatter([0],[0],marker='s',s=70,color='k',zorder=5)
ax.annotate('pre-industrial',(0,-0.1),fontsize=7.5,ha='left',va='top',xytext=(0.25,-0.7),
            arrowprops=dict(arrowstyle='-',lw=.6,color='0.4'))
# labels next to markers
lab_pos={'LGM':(F(190)+0.35,-6.4),'MPWP':(F(400)+0.4,3.1),'EECO':(F(1470)+0.6,13.4),
         'LIG':(F(275)-0.25,1.6),'MH':(F(264)-0.3,-1.9)}
names={'LGM':'LGM (21 ka)','MPWP':'mPWP (3.3 Ma)','EECO':'EECO (50 Ma)',
       'LIG':'LIG (127 ka)','MH':'Mid-Holocene (6 ka)'}
cols={**{k:v[3] for k,v in P.items()},**{k:v[3] for k,v in extra.items()}}
ha={'LGM':'left','MPWP':'left','EECO':'left','LIG':'right','MH':'right'}
for k,(x,y) in lab_pos.items():
    ax.annotate(names[k],(x,y),fontsize=8,color=cols[k],ha=ha[k],fontweight='bold')
# legend for marker semantics
from matplotlib.lines import Line2D
handles=[Line2D([],[],marker='o',ls='',mfc='0.4',mec='0.4',ms=10,label='proxy assessment (protocol period)'),
         Line2D([],[],marker='o',ls='',mfc='white',mec='0.4',ms=10,label='proxy assessment (context)'),
         Line2D([],[],marker='o',ls='',mfc='0.4',mec='none',ms=4,label='individual model simulations'),
         Line2D([],[],marker='s',ls='',color='k',ms=8,label='pre-industrial')]
ax.legend(handles=handles,fontsize=7,loc='upper left',frameon=True,framealpha=.9)
ax.set_xlabel('CO$_2$ radiative forcing relative to pre-industrial (W m$^{-2}$)')
ax.set_ylabel('$\\Delta$GMST relative to pre-industrial (K)')
ax.set_xlim(-3.4,13); ax.set_ylim(-9,19.5)
ax.axhline(0,color='0.8',lw=.5,zorder=0); ax.axvline(0,color='0.8',lw=.5,zorder=0)
for s in ['top','right']: ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig('paleo_lever.png',dpi=200,bbox_inches='tight')
fig.savefig('paleo_lever.pdf',bbox_inches='tight')
print('model counts:', mod.groupby('period').size().to_dict())
print('saved')
