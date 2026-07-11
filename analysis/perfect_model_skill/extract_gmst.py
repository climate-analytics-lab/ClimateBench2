import intake, numpy as np, xarray as xr, pandas as pd, warnings, os, glob
warnings.filterwarnings('ignore')
os.makedirs('gmst_cache', exist_ok=True)
cat = intake.open_esm_datastore('https://storage.googleapis.com/cmip6/pangeo-cmip6.json')

def gmst_for(source, exp):
    q = cat.search(source_id=source, experiment_id=exp, variable_id='tas',
                   table_id='Amon', member_id='r1i1p1f1')
    if len(q.df)==0: return None
    ds = xr.open_zarr(q.df.zstore.values[0], storage_options={'token':'anon'},
                      consolidated=True, decode_times=True)
    w = np.cos(np.deg2rad(ds['lat']))
    gm = ds['tas'].weighted(w).mean(('lat','lon')).groupby('time.year').mean('time')
    return gm.compute()

cat2 = cat.search(variable_id='tas', table_id='Amon',
                  experiment_id=['historical','ssp245'], member_id='r1i1p1f1')
df = cat2.df
both = sorted([m for m,s in df.groupby('source_id')['experiment_id'].apply(set).items()
               if {'historical','ssp245'}<=s])
for i,m in enumerate(both):
    fn=f'gmst_cache/{m}.csv'
    if os.path.exists(fn):
        print(f"[{i+1}/{len(both)}] {m}: cached", flush=True); continue
    try:
        h=gmst_for(m,'historical'); s=gmst_for(m,'ssp245')
        if h is None or s is None: print(f"skip {m}",flush=True); continue
        h=h.sel(year=slice(1950,2014)); s=s.sel(year=slice(2015,2060))
        ser=xr.concat([h,s],dim='year').to_series()
        ser=ser[~ser.index.duplicated()]
        ser.to_csv(fn)
        print(f"[{i+1}/{len(both)}] {m}: {int(ser.index.min())}-{int(ser.index.max())} n={len(ser)}",flush=True)
    except Exception as e:
        print(f"FAIL {m}: {type(e).__name__} {str(e)[:70]}",flush=True)
# assemble
rows={}
for f in glob.glob('gmst_cache/*.csv'):
    m=os.path.basename(f)[:-4]
    s=pd.read_csv(f,index_col=0).iloc[:,0]; rows[m]=s
out=pd.DataFrame(rows); out.index.name='year'
out.to_csv('gmst_cmip6.csv')
print("assembled", out.shape, flush=True)
