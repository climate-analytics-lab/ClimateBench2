"""
Illustrative perfect-model test of the ClimateBench v2 core assumption:
does skill at recent (pre-2015) global-mean warming predict skill at the
mid-century (2050) change? Uses CMIP6 GMST (tas, Amon, r1i1p1f1), historical+ssp245,
from the Pangeo Google-Cloud archive. See Watson-Parris et al. (2023,
doi:10.1029/2023MS003926) for a fuller perfect-model emulation treatment.
"""
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from scipy import stats

d=pd.read_csv('gmst_cmip6.csv',index_col=0)
need=list(range(1975,2051)); d=d.loc[:,[m for m in d.columns if d.loc[need,m].notna().all()]]
base=d.loc[1990:2020].mean(); an=d-base; models=list(an.columns); M=len(models)
def trend(m,a,b): 
    y=np.arange(a,b+1); return np.polyfit(y,an[m].loc[a:b].values,1)[0]*10
present=np.array([trend(m,1975,2014) for m in models])          # K/decade, pre-2015 ("seen")
future =np.array([an[m].loc[2041:2050].mean() for m in models]) # K, 2050 change vs 1990-2020

r,_=stats.pearsonr(present,future); R2=r**2
# leave-one-out cross-validated prediction of 2050 change from recent trend
pred=np.zeros(M)
for i in range(M):
    m=np.arange(M)!=i; s,ic=np.polyfit(present[m],future[m],1); pred[i]=s*present[i]+ic
cvR2=1-np.sum((future-pred)**2)/np.sum((future-future.mean())**2)
cvRMSE=np.sqrt(np.mean((future-pred)**2)); climRMSE=future.std()
print(f"N={M}  across-model r={r:.2f} R2={R2:.2f}  CV_R2={cvR2:.2f}  CV_RMSE={cvRMSE:.2f}K  clim_RMSE={climRMSE:.2f}K")

ACC='#2166ac'; ACC2='#b2182b'; G='#555'
fig,ax=plt.subplots(1,2,figsize=(9.6,4.2))
# (a) emergent relationship
ax[0].scatter(present,future,s=36,color=ACC,alpha=.85,edgecolor='w',lw=.5,zorder=3)
xx=np.linspace(present.min(),present.max(),50); s,ic=np.polyfit(present,future,1)
ax[0].plot(xx,s*xx+ic,color=ACC2,lw=1.7,zorder=2)
for lab in ['CanESM5','INM-CM4-8','MPI-ESM1-2-LR']:
    if lab in models:
        i=models.index(lab); ax[0].annotate(lab,(present[i],future[i]),fontsize=7,color=G,
            xytext=(4,-2),textcoords='offset points')
ax[0].set_xlabel('Recent warming rate  (GMST trend 1975–2014, K decade$^{-1}$)')
ax[0].set_ylabel('2050 change  (2041–2050 vs 1990–2020, K)')
ax[0].set_title('(a) Recent warming is a partial constraint',fontsize=10,loc='left')
ax[0].text(.05,.90,f'r = {r:.2f}   R$^2$ = {R2:.2f}',transform=ax[0].transAxes,fontsize=10,color=ACC2,fontweight='bold')
ax[0].grid(alpha=.25,lw=.5); [ax[0].spines[k].set_visible(False) for k in['top','right']]
# (b) leave-one-out CV predicted vs actual
lo=min(future.min(),pred.min())-.1; hi=max(future.max(),pred.max())+.1
ax[1].plot([lo,hi],[lo,hi],color=G,lw=1,ls='--',zorder=1)
ax[1].scatter(future,pred,s=36,color=ACC,alpha=.85,edgecolor='w',lw=.5,zorder=3)
ax[1].set_xlim(lo,hi); ax[1].set_ylim(lo,hi)
ax[1].set_xlabel('Actual 2050 change (K)')
ax[1].set_ylabel('Predicted from recent trend (K)')
ax[1].set_title('(b) Leave-one-out prediction of a held-out model',fontsize=10,loc='left')
ax[1].text(.05,.90,f'CV R$^2$ = {cvR2:.2f}',transform=ax[1].transAxes,fontsize=10,color=ACC2,fontweight='bold')
ax[1].grid(alpha=.25,lw=.5); [ax[1].spines[k].set_visible(False) for k in['top','right']]
fig.tight_layout()
fig.savefig('present_future_skill_correlation.png',dpi=200,bbox_inches='tight')
fig.savefig('present_future_skill_correlation.pdf',bbox_inches='tight')
pd.DataFrame({'model':models,'recent_trend_Kdec':present,'change2050_K':future,'cv_pred_K':pred}).to_csv('skill_summary.csv',index=False)
print("saved figure + skill_summary.csv")
