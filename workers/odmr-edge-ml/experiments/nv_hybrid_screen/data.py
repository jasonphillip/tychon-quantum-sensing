"""Fresh development-only data; excludes all historical data and seed namespaces."""
import argparse,json
from pathlib import Path
import numpy as np
from guard import authorize,seed,output,write,sha
from physics import Point,forward,F,FACTOR,PHOTONS
def main():
    p=argparse.ArgumentParser();p.add_argument("--approval",required=True);p.add_argument("--out",required=True)
    p.add_argument("--split",choices=("train","development","nuisance"),required=True);a=p.parse_args()
    auth=authorize(a.approval,"generate_"+a.split);entropy=seed(auth,a.split)
    out=output(a.out)
    config=json.loads((Path(__file__).parent/"protocol.json").read_text());n=config["sizes"][a.split]
    rng=np.random.default_rng(entropy);spectra=[];labels=[];parameters=[];means=[];nuisance=[]
    for i in range(n):
        def uniform(key):return rng.uniform(*config["priors"][key])
        B=uniform("field_uT");T=uniform("temperature_K")
        if a.split=="nuisance":
            T=rng.uniform(*config["nuisance_holdout"]["temperature_K"][int(rng.integers(0,2))])
        mw=uniform("mw_scale");gradient=uniform("gradient");width=uniform("width_mhz")
        contrast=uniform("contrast");slope=uniform("slope");baseline=uniform("baseline")
        point=Point(field_uT=B,bias_uT=250,width_mhz=width,temperature_K=T,mw_scale=mw,
                    gradient=gradient,contrast=contrast,slope=slope)
        mean,_=forward(point,"fixed_amplitude",FACTOR);mean=mean+baseline-1
        noise=rng.standard_normal(100);observed=mean+np.sqrt(mean/PHOTONS)*noise
        spectra.append(observed);means.append(mean);labels.append(B)
        parameters.append([B,2871-.0742*(T-300),width,contrast,baseline,slope])
        nuisance.append([T,mw,gradient])
    np.savez_compressed(out/"inputs.npz",spectra=np.array(spectra),frequencies_mhz=F)
    np.savez_compressed(out/"truth.npz",field=np.array(labels),parameters=np.array(parameters),mean=np.array(means),nuisance=np.array(nuisance))
    write(out/"manifest.json",{"split":a.split,"rows":n,"seed":entropy,"approval_sha256":auth["approval_sha256"],
        "files":{k:sha(out/k) for k in ("inputs.npz","truth.npz")},"scope":"development only"})
if __name__=="__main__":main()
