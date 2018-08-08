""" Module for PYPIT extraction code
"""
from __future__ import (print_function, absolute_import, division, unicode_literals)

import time
import copy
import inspect

import numpy as np

from matplotlib import pyplot as plt
from matplotlib import gridspec, font_manager

from astropy import units
from astropy.stats import sigma_clip
from astropy.stats import sigma_clipped_stats

from pypeit import msgs
from pypeit.core import qa
from pypeit import artrace
from pypeit import utils
from pypeit.core import pixels
from pypeit import debugger
from pypeit import ginga

# MASK VALUES FROM EXTRACTION
# 0 
# 2**0 = Flagged as bad detector pixel
# 2**1 = Flagged as affected by Cosmic Ray 
# 2**5 = Flagged as NAN (from something gone wrong)
# 2**6 = Entire region masked

mask_flags = dict(bad_pix=2**0, CR=2**1, NAN=2**5, bad_row=2**6)






def extract_asymbox2(image,left_in,right_in,ycen = None,weight_image = None):
    """ Extract the total flux within a variable window at many positions. This routine will accept an asymmetric/variable window
    specified by the left_in and right_in traces.  The ycen position is optional. If it is not provied, it is assumed to be integers
    in the spectral direction (as is typical for traces). Traces are expected to run vertically to be consistent with other
    extract_  routines. Based on idlspec2d/spec2d/extract_asymbox2.pro

    Parameters
    ----------
    image :  float ndarray
        Image to extract from. It is a 2-d array with shape (nspec, nspat)
    left  :  float ndarray
        Left boundary of region to be extracted (given as floating pt pixels). This can either be an 2-d  array with shape
        (nspec, nTrace) array, or a 1-d array with shape (nspec) forthe case of a single trace.

    right  :  float ndarray
        Right boundary of region to be extracted (given as floating pt pixels). This can either be an 2-d  array with shape
        (nspec, nTrace) array, or a 1-d array with shape (nspec) forthe case of a single trace.


    Optional Parameters
    -------------------
    ycen :  float ndarray
        Y positions corresponding to "Left"  and "Right" (expected as integers). Will be cast to an integer if floats
        are provided. This needs to have the same shape as left and right broundarys provided above. In other words,
        either a  2-d  array with shape (nspec, nTrace) array, or a 1-d array with shape (nspec) forthe case of a single trace.

    weight_image: float ndarray
        Weight map to be applied to image before boxcar. It is a 2-d array with shape (nspec, nspat)

    Returns
    -------
    fextract:   ndarray
       Extracted flux at positions specified by (left<-->right, ycen). The output will have the same shape as
       Left and Right, i.e.  an 2-d  array with shape (nspec, nTrace) array if multiple traces were input, or a 1-d array with shape (nspec) for
       the case of a single trace.


    Revision History
    ----------------
    24-Mar-1999  Written by David Schlegel, Princeton.
    17-Feb-2003  Written with slow IDL routine, S. Burles, MIT
    22-Apr-2018  Ported to python by Joe Hennawi
    """

    # ToDO it would be nice to avoid this transposing, but I got confused during the IDL port
    left = left_in.T
    right = right_in.T

    dim = left.shape
    ndim = left.ndim
    if (ndim == 1):
        nTrace = 1
        npix = dim[0]
    else:
        nTrace = dim[0]
        npix = dim[1]

    if ycen is None:
        if ndim == 1:
            ycen_out = np.arange(npix, dtype='int')
        elif ndim == 2:
            ycen_out = np.outer(np.ones(nTrace, dtype='int'), np.arange(npix, dtype='int'), )
        else:
            raise ValueError('trace is not 1 or 2 dimensional')
    else:
        ycen_out = ycen.T
        ycen_out = np.rint(ycen_out).astype(int)

    if ((np.size(left) != np.size(ycen_out)) | (np.shape(left) != np.shape(ycen_out))):
        raise ValueError('Number of elements and left of trace and ycen must be equal')

    idims = image.shape
    nspat = idims[1]
    nspec = idims[0]

    maxwindow = np.max(right - left)
    tempx = np.int(maxwindow + 3.0)

    bigleft = np.outer(left[:], np.ones(tempx))
    bigright = np.outer(right[:], np.ones(tempx))
    spot = np.outer(np.ones(npix * nTrace), np.arange(tempx)) + bigleft - 1
    bigy = np.outer(ycen_out[:], np.ones(tempx, dtype='int'))

    fullspot = np.array(np.fmin(np.fmax(np.round(spot + 1) - 1, 0), nspat - 1), int)
    fracleft = np.fmax(np.fmin(fullspot - bigleft, 0.5), -0.5)
    fracright = np.fmax(np.fmin(bigright - fullspot, 0.5), -0.5)
    del bigleft
    del bigright
    bool_mask1 = (spot >= -0.5) & (spot < (nspat - 0.5))
    bool_mask2 = (bigy >= 0) & (bigy <= (nspec - 1))
    weight = (np.fmin(np.fmax(fracleft + fracright, 0), 1)) * bool_mask1 * bool_mask2
    del spot
    del fracleft
    del fracright
    bigy = np.fmin(np.fmax(bigy, 0), nspec - 1)

    if weight_image != None:
        temp = np.array([weight_image[x1, y1] * image[x1, y1] for (x1, y1) in zip(bigy.flatten(), fullspot.flatten())])
        temp2 = np.reshape(weight.flatten() * temp, (nTrace, npix, tempx))
        fextract = np.sum(temp2, axis=2)
        temp_wi = np.array([weight_image[x1, y1] for (x1, y1) in zip(bigy.flatten(), fullspot.flatten())])
        temp2_wi = np.reshape(weight.flatten() * temp_wi, (nTrace, npix, tempx))
        f_ivar = np.sum(temp2_wi, axis=2)
        fextract = fextract / (f_ivar + (f_ivar == 0)) * (f_ivar > 0)
    else:
        # Might be more pythonic way to code this. I needed to switch the flattening order in order to get
        # this to work
        temp = np.array([image[x1, y1] for (x1, y1) in zip(bigy.flatten(), fullspot.flatten())])
        temp2 = np.reshape(weight.flatten() * temp, (nTrace, npix, tempx))
        fextract = np.sum(temp2, axis=2)

    # IDL version model functionality not implemented yet
    # At the moment I'm not reutnring the f_ivar for the weight_image mode. I'm not sure that this functionality is even
    # ever used

    if(nTrace ==1):
        fextract = fextract.reshape(npix)
    return fextract.T


def extract_boxcar(image,trace_in, radius_in, ycen = None):
    """ Extract the total flux within a boxcar window at many positions. The ycen position is optional. If it is not provied, it is assumed to be integers
     in the spectral direction (as is typical for traces). Traces are expected to run vertically to be consistent with other
     extract_  routines. Based on idlspec2d/spec2d/extract_boxcar.pro

     Parameters
     ----------
     image :  float ndarray
         Image to extract from. It is a 2-d array with shape (nspec, nspat)

     trace_in :  float ndarray
         Trace for the region to be extracted (given as floating pt pixels). This can either be an 2-d  array with shape
         (nspec, nTrace) array, or a 1-d array with shape (nspec) forthe case of a single trace.

     radius :  float or ndarray
         boxcar radius in floating point pixels. This can be either be in put as a scalar or as an array to perform
         boxcar extraction a varaible radius. If an array is input it must have the same size and shape as trace_in, i.e.
         a 2-d  array with shape (nspec, nTrace) array, or a 1-d array with shape (nspec) for the case of a single trace.


     Optional Parameters
     -------------------
     ycen :  float ndarray
         Y positions corresponding to trace_in (expected as integers). Will be rounded to the nearest integer if floats
         are provided. This needs to have the same shape as trace_in  provided above. In other words,
         either a  2-d  array with shape (nspec, nTrace) array, or a 1-d array with shape (nspec) forthe case of a single trace.


     Returns
     -------
     fextract:   ndarray
         Extracted flux at positions specified by (left<-->right, ycen). The output will have the same shape as
         Left and Right, i.e.  an 2-d  array with shape (nspec, nTrace) array if multiple traces were input, or a 1-d array with shape (nspec) for
         the case of a single trace.

     Revision History
     ----------------
     24-Mar-1999  Written by David Schlegel, Princeton.
     22-Apr-2018  Ported to python by Joe Hennawi
     """


    # Checks on radius
    if (isinstance(radius_in,int) or isinstance(radius_in,float)):
        radius = radius_in
    elif ((np.size(radius)==np.size(trace_in)) & (np.shape(radius) == np.shape(trace_in))):
        radius = radius_in.T
    else:
        raise ValueError('Boxcar radius must a be either an integer, a floating point number, or an ndarray '
                         'with the same shape and size as trace_in')

    trace = trace_in.T

    dim = trace.shape
    ndim = len(dim)
    if (ndim == 1):
        nTrace = 1
        npix = dim[0]
    else:
        nTrace = dim[0]
        npix = dim[1]

    if ycen is None:
        if ndim == 1:
            ycen_out = np.arange(npix, dtype='int')
        elif ndim == 2:
            ycen_out = np.outer(np.ones(nTrace, dtype='int'), np.arange(npix, dtype='int'), )
        else:
            raise ValueError('trace is not 1 or 2 dimensional')
    else:
        ycen_out = ycen.T
        ycen_out = np.rint(ycen_out).astype(int)

    if ((np.size(trace) != np.size(ycen_out)) | (np.shape(trace) != np.shape(ycen_out))):
        raise ValueError('Number of elements and shape of trace and ycen must be equal')



    left = trace - radius
    right = trace + radius
    fextract = extract_asymbox2(image, left, right, ycen_out)

    return fextract




def extract_optimal(sciimg,ivar, mask, waveimg, skyimg, rn2_img, oprof, box_radius, specobj):

    """ Calculate the spatial FWHM from an object profile. Utitlit routine for fit_profile

    Parameters
    ----------
    sciimg : float ndarray shape (nspec, nspat)
       Science frame
    ivar: float ndarray shape (nspec, nspat)
       inverse variance of science frame. Can be a model or deduced from the image itself.
    mask: boolean ndarray
       mask indicating which pixels are good. Good pixels = True, Bad Pixels = False
    waveimg :  float ndarray
        Wavelength image. float 2-d array with shape (nspec, nspat)
    skyimg: float ndarray shape (nspec, nspat)
        Image containing our model of the sky
    rn2_img: float ndarray shape (nspec, nspat)
        Image containing the read noise squared (including digitization noise due to gain, i.e. this is an effective read noise)
    oprof: float ndarray shape (nspec, nspat)
        Image containing the profile of the object that we are extracting
    box_radius: float
        Size of boxcar window in floating point pixels in the spatial direction.
    specobj: SpecObj object (from the SpecObj class in specobj.py). This is the container that holds object, trace,
    and extraction information for the object in question. This routine operates one object at a time.

    Returns
    -------
    Return value is None. The specobj object is changed in place with the boxcar and optimal dictionaries being filled
    with the extraction parameters.

    Revision History
    ----------------
    11-Mar-2005  Written by J. Hennawi and S. Burles.
    28-May-2018  Ported to python by J. Hennawi
    """

    imgminsky = sciimg - skyimg
    nspat = imgminsky.shape[1]
    nspec = imgminsky.shape[0]

    spec_vec = np.arange(nspec)
    spat_vec = np.arange(nspat)

    var_no = np.abs(skyimg - np.sqrt(2.0) * np.sqrt(rn2_img)) + rn2_img

    ispec, ispat = np.where(oprof > 0.0)
    mincol = np.min(ispat)
    maxcol = np.max(ispat) + 1
    nsub = maxcol - mincol

    mask_sub = mask[:,mincol:maxcol]
    wave_sub = waveimg[:,mincol:maxcol]
    ivar_sub = np.fmax(ivar[:,mincol:maxcol],0.0) # enforce positivity since these are used as weights
    vno_sub = np.fmax(var_no[:,mincol:maxcol],0.0)

    rn2_sub = rn2_img[:,mincol:maxcol]
    img_sub = imgminsky[:,mincol:maxcol]
    sky_sub = skyimg[:,mincol:maxcol]
    oprof_sub = oprof[:,mincol:maxcol]
    # enforce normalization and positivity of object profiles
    norm = np.nansum(oprof_sub,axis = 1)
    norm_oprof = np.outer(norm, np.ones(nsub))
    oprof_sub = np.fmax(oprof_sub/norm_oprof, 0.0)

    ivar_denom = np.nansum(mask_sub*oprof_sub, axis=1)
    mivar_num = np.nansum(mask_sub*ivar_sub*oprof_sub**2, axis=1)
    mivar_opt = mivar_num/(ivar_denom + (ivar_denom == 0.0))
    flux_opt = np.nansum(mask_sub*ivar_sub*img_sub*oprof_sub, axis=1)/(mivar_num + (mivar_num == 0.0))
    # Optimally extracted noise variance (sky + read noise) only. Since
    # this variance is not the same as that used for the weights, we
    # don't get the usual cancellation. Additional denom factor is the
    # analog of the numerator in Horne's variance formula. Note that we
    # are only weighting by the profile (ivar_sub=1) because
    # otherwise the result depends on the signal (bad).
    nivar_num =np.nansum(mask_sub*oprof_sub**2, axis=1) # Uses unit weights
    nvar_opt = ivar_denom*((mask_sub*vno_sub*oprof_sub**2).sum(axis=1))/(nivar_num**2 + (nivar_num**2 == 0.0))
    nivar_opt = 1.0/(nvar_opt + (nvar_opt == 0.0))
    # Optimally extract sky and (read noise)**2 in a similar way
    sky_opt = ivar_denom*(np.nansum(mask_sub*sky_sub*oprof_sub**2, axis=1))/(nivar_num**2 + (nivar_num**2 == 0.0))
    rn2_opt = ivar_denom*(np.nansum(mask_sub*rn2_sub*oprof_sub**2, axis=1))/(nivar_num**2 + (nivar_num**2 == 0.0))
    rn_opt = np.sqrt(rn2_opt)
    rn_opt[np.isnan(rn_opt)]=0.0

    tot_weight = np.nansum(mask_sub*ivar_sub*oprof_sub, axis=1)
    mask_opt = (tot_weight > 0.0) & (mivar_num > 0.0) & (ivar_denom > 0.0)
    frac_use = np.nansum((mask_sub*ivar_sub > 0.0)*oprof_sub, axis=1)
    # Use the same weights = oprof^2*mivar for the wavelenghts as the flux.
    # Note that for the flux, one of the oprof factors cancels which does
    # not for the wavelengths.
    wave_opt = np.nansum(mask_sub*ivar_sub*wave_sub*oprof_sub**2, axis=1)/(mivar_num + (mivar_num == 0.0))
    # Interpolate wavelengths over masked pixels
    badwvs = (mivar_num <= 0) | (np.isfinite(wave_opt) == False) | (wave_opt <= 0.0)
    if badwvs.any():
        oprof_smash = np.nansum(oprof_sub**2, axis=1)
        # Can we use the profile average wavelengths instead?
        oprof_good = badwvs & (oprof_smash > 0.0)
        if oprof_good.any():
            wave_opt[oprof_good] = np.nansum(wave_sub[oprof_good,:]*oprof_sub[oprof_good,:]**2, axis=1)/np.nansum(oprof_sub[oprof_good,:]**2, axis=1)
        oprof_bad = badwvs & ((oprof_smash <= 0.0) | (np.isfinite(oprof_smash) == False) | (wave_opt <= 0.0) | (np.isfinite(wave_opt) == False))
        if oprof_bad.any():
            # For pixels with completely bad profile values, interpolate from trace.
            f_wave = RectBivariateSpline(spec_vec,spat_vec, waveimg)
            wave_opt[oprof_bad] = f_wave(specobj.trace_spec[oprof_bad], specobj.trace_spat[oprof_bad],grid=False)

    flux_model = np.outer(flux_opt,np.ones(nsub))*oprof_sub
    chi2_num = np.nansum((img_sub - flux_model)**2*ivar_sub*mask_sub,axis=1)
    chi2_denom = np.fmax(np.nansum(ivar_sub*mask_sub > 0.0, axis=1) - 1.0, 1.0)
    chi2 = chi2_num/chi2_denom

    # Fill in the optimally extraction tags
    specobj.optimal['WAVE_OPT'] = wave_opt    # Optimally extracted wavelengths
    specobj.optimal['FLUX_OPT'] = flux_opt    # Optimally extracted flux
    specobj.optimal['IVAR_OPT'] = mivar_opt   # Inverse variance of optimally extracted flux using modelivar image
    specobj.optimal['NIVAR_OPT'] = nivar_opt  # Optimally extracted noise variance (sky + read noise) only
    specobj.optimal['MASK_OPT'] = mask_opt    # Mask for optimally extracted flux
    specobj.optimal['SKY_OPT'] = sky_opt      # Optimally extracted sky
    specobj.optimal['RN_OPT'] = rn_opt        # Square root of optimally extracted read noise squared
    specobj.optimal['FRAC_USE'] = frac_use    # Fraction of pixels in the object profile subimage used for this extraction
    specobj.optimal['CHI2'] = chi2            # Reduced chi2 of the model fit for this spectral pixel

    # Fill in the boxcar extraction tags
    flux_box  = extract_boxcar(imgminsky*mask, specobj.trace_spat,box_radius, ycen = specobj.trace_spec)
    # Denom is computed in case the trace goes off the edge of the image
    box_denom = extract_boxcar(waveimg*mask > 0.0, specobj.trace_spat,box_radius, ycen = specobj.trace_spec)
    wave_box  = extract_boxcar(waveimg*mask, specobj.trace_spat,box_radius, ycen = specobj.trace_spec)/(box_denom + (box_denom == 0.0))
    varimg = 1.0/(ivar + (ivar == 0.0))
    var_box  = extract_boxcar(varimg*mask, specobj.trace_spat,box_radius, ycen = specobj.trace_spec)
    nvar_box  = extract_boxcar(var_no*mask, specobj.trace_spat,box_radius, ycen = specobj.trace_spec)
    sky_box  = extract_boxcar(skyimg*mask, specobj.trace_spat,box_radius, ycen = specobj.trace_spec)
    rn2_box  = extract_boxcar(rn2_img*mask, specobj.trace_spat,box_radius, ycen = specobj.trace_spec)
    rn_posind = (rn2_box > 0.0)
    rn_box = np.zeros(rn2_box.shape,dtype=float)
    rn_box[rn_posind] = np.sqrt(rn2_box[rn_posind])
    pixtot  = extract_boxcar(ivar*0 + 1.0, specobj.trace_spat,box_radius, ycen = specobj.trace_spec)
    # If every pixel is masked then mask the boxcar extraction
    mask_box = (extract_boxcar(ivar*mask == 0.0, specobj.trace_spat,box_radius, ycen = specobj.trace_spec) != pixtot)

    bad_box = (wave_box <= 0.0) | (np.isfinite(wave_box) == False) | (box_denom == 0.0)
    # interpolate bad wavelengths over masked pixels
    if bad_box.any():
        f_wave = RectBivariateSpline(spec_vec, spat_vec, waveimg)
        wave_box[bad_box] = f_wave(specobj.trace_spec[bad_box], specobj.trace_spat[bad_box],grid=False)

    ivar_box = 1.0/(var_box + (var_box == 0.0))
    nivar_box = 1.0/(nvar_box + (nvar_box == 0.0))

    specobj.boxcar['WAVE_BOX'] = wave_box
    specobj.boxcar['FLUX_BOX'] = flux_box*mask_box
    specobj.boxcar['IVAR_BOX'] = ivar_box*mask_box
    specobj.boxcar['NIVAR_BOX'] = nivar_box*mask_box
    specobj.boxcar['MASK_BOX'] = mask_box
    specobj.boxcar['SKY_BOX'] = sky_box
    specobj.boxcar['RN_BOX'] = rn_box

    return None




def findfwhm(model, sig_x):
    """ Calculate the spatial FWHM from an object profile. Utitlit routine for fit_profile

    Parameters
    ----------
    model :   numpy float 2-d array [nspec, nspat]
    x :

    Returns
    -------
    peak :  Peak value of the profile model
    peak_x:  sig_x location where the peak value is obtained
    lwhm:   Value of sig_x at the left width at half maximum
    rwhm:   Value of sig_x at the right width at half maximum

    Revision History
    ----------------
    11-Mar-2005  Written by J. Hennawi and S. Burles David Schlegel, Princeton.
    28-May-2018  Ported to python by J. Hennawi
    """


    peak = (model*(np.abs(sig_x) < 1.)).max()
    peak_x = sig_x[(model*(np.abs(sig_x) < 1.)).argmax()]

    lrev = ((sig_x < peak_x) & (model < 0.5*peak))[::-1]
    lind, = np.where(lrev)
    if(lind.size > 0):
        lh = lind.min()
        lwhm = (sig_x[::-1])[lh]
    else:
        lwhm = -0.5*2.3548

    rind, = np.where((sig_x > peak_x) & (model < 0.5*peak))
    if(rind.size > 0):
        rh = rind.min()
        rwhm = sig_x[rh]
    else:
        rwhm = 0.5 * 2.3548

    return (peak, peak_x, lwhm, rwhm)



def fit_profile_qa(x_tot,y_tot, model_tot, l_limit = None, r_limit = None, ind = None,
                   title =' ', xtrunc = 1e6, xlim = None, ylim = None, qafile = None):


    # Plotting pre-amble
    plt.close("all")
#    plt.rc('text', usetex=True)
#    plt.rc('font', family='serif')
    width = 10.0 # Golden ratio 1.618
    fig, ax = plt.subplots(1, figsize=(width, width/1.618))

    if ind is None:
        ind = np.slice(x_tot.size)

    x = x_tot.flat[ind]
    y = y_tot.flat[ind]
    model = model_tot.flat[ind]

    ax.plot(x,y,color='k',marker='o',markersize= 0.3, mfc='k',fillstyle='full',linestyle='None')


    max_model = np.fmin(model.max(), 2.0)
    if xlim is None:
        goodpix = model > 0.001*max_model
        if goodpix.any():
            minx = np.fmax(1.1*(x[goodpix]).min(), -xtrunc)
            maxx = np.fmin(1.1*(x[goodpix]).max(),  xtrunc)
        else:
            minx = -5.0
            maxx = 5.0
    else:
        minx = -xlim
        maxx = xlim
    xlimit = (minx, maxx)

    nsamp = 150
    half_bin = (maxx - minx)/nsamp/2.0
    if ylim is None:
        ymax = np.fmax(1.5*model.max(), 0.3)
        ymin = np.fmin(-0.1*ymax, -0.05)
        ylim = (ymin, ymax)
    plot_mid = (np.arange(nsamp) + 0.5)/nsamp*(maxx - minx) + minx

    y20 = np.zeros(nsamp)
    y80 = np.zeros(nsamp)
    y50 = np.zeros(nsamp)
    model_samp = np.zeros(nsamp)
    nbin = np.zeros(nsamp)

    for i in range(nsamp):
        dist = np.abs(x - plot_mid[i])
        close = dist < half_bin
        yclose = y[close]
        nclose = close.sum()
        nbin[i] = nclose
        if close.any():
            closest = (dist[close]).argmin()
            model_samp[i] = (model[close])[closest]
        if nclose > 3:
            s = yclose.argsort()
            y50[i] = yclose[s[int(np.rint((nclose - 1)*0.5))]]
            y80[i] = yclose[s[int(np.rint((nclose - 1)*0.8))]]
            y20[i] = yclose[s[int(np.rint((nclose - 1)*0.2))]]
            ax.plot([plot_mid[i],plot_mid[i]], [y20[i],y80[i]], linewidth=1.0, color='cornflowerblue')

    icl = nbin > 3
    if icl.any():
        ax.plot(plot_mid[icl],y50[icl],marker = 'o', color='lime', markersize=2, fillstyle='full', linestyle='None')
    else:
        ax.plot(plot_mid, y50, marker='o', color='lime', markersize=2, fillstyle = 'full', linestyle='None')

    isort = x.argsort()
    ax.plot(x[isort], model[isort], color='red', linewidth=1.0)



    if l_limit is not None:
        ax.axvline(x =l_limit, color='orange',linewidth=1.0)
    if r_limit is not None:
        ax.axvline(x=r_limit, color='orange',linewidth=1.0)

    ax.set_xlim(xlimit)
    ax.set_ylim(ylim)
    ax.set_title(title)
    ax.set_xlabel(r'$x/\sigma$')
    ax.set_ylabel('Normalized Profile')

    fig.subplots_adjust(left=0.15, right=0.9, top=0.9, bottom=0.15)
    plt.show()
    return


def fit_profile(image, ivar, waveimg, trace_in, wave, flux, fluxivar,
                thisfwhm=4.0, MAX_TRACE_CORR = 2.0, SN_GAUSS = 3.0, wvmnx = [2900.0,30000.0],
                hwidth = None, PROF_NSIGMA = None, NO_DERIV = False, GAUSS = False):

    """Fit a non-parametric object profile to an object spectrum, unless the S/N ratio is low (> SN_GAUSS) in which
    fit a simple Gaussian. Port of IDL LOWREDUX long_gprofile.pro

     Parameters
     ----------
     image : numpy float 2-d array [nspec, nspat]
         sky-subtracted image
     ivar : numpy float 2-d array [nspec, nspat]
         inverse variance of sky-subtracted image
     waveimg numpy float 2-d array [nspec, nspat]
         2-d wavelength map
     trace_in : numpy 1-d array [nspec]
         object trace
     wave : numpy 1-d array [nspec]
         extracted wavelength of spectrum
     flux : numpy 1-d array [nspec]
         extracted flux of spectrum
     fluxivar : numpy 1-d array [nspec]
         inverse variance of extracted flux spectrum


    Optional Parameters
    ----------
    thisfwhm : float
         fwhm of the object trace
    MAX_TRACE_CORR : float [default = 2.0]
         maximum trace correction to apply
    SN_GAUSS : float [default = 3.0]
         S/N ratio below which code just uses a Gaussian
    wvmnx : float [default = [2900.0,30000.0]
         wavelength range of usable part of spectrum
    hwidth : float [default = None]
         object maskwidth determined from object finding algorithm. If = None,
         code defaults to use 3.0*(np.max(thisfwhm) + 1.0)
    PROF_NSIGMA : float [default = None]
         Number of sigma to include in the profile fitting. This option is only needed for bright objects that are not
         point sources, which allows the profile fitting to fit the high S/N wings (rather than the default behavior
         which truncates exponentially). This allows for extracting all the flux and results in better sky-subtraction
         for bright extended objects.
    NO_DERIV : boolean [default = False]
         disables determination of derivatives and exponential tr

     Returns
     -------
     :func:`tuple`
         A tuple containing the (sset, outmask, yfit, reduced_chi), where

            sset: object
               bspline object
            outmask: : :class:`numpy.ndarray`
               output mask which the same size as xdata
            yfit  : :class:`numpy.ndarray`
               result of the bspline fit (same size as xdata)
            reduced_chi: float
               value of the reduced chi^2
     """

    from scipy.interpolate import interp1d
    from scipy.ndimage.filters import median_filter
    from pypeit.core.pydl import bspline
    from pypeit.core.pydl import iterfit as  bspline_iterfit
    from pypeit.core.pydl import djs_maskinterp
    from pypeit.utils import bspline_profile
    from scipy.special import erfcinv

    if hwidth is None: 3.0*(np.max(thisfwhm) + 1.0)
    if PROF_NSIGMA is not None:
        NO_DERIV = True

    thisfwhm = np.fmax(thisfwhm,1.0) # require the FWHM to be greater than 1 pixel

    xnew = trace_in

    nspat = image.shape[1]
    nspec = image.shape[0]

    # create some images we will need
    sub_obj = image
    sub_ivar = ivar
    sub_wave = waveimg
    sub_trace = trace_in
    sub_x = np.arange(nspat)
    sn2_sub = np.zeros((nspec,nspat))
    spline_sub = np.zeros((nspec,nspat))


    flux_sm = median_filter(flux, size=5, mode = 'reflect')
    fluxivar_sm =  median_filter(fluxivar, size = 5, mode = 'reflect')
#    flux_sm = djs_median(flux, width = 5, boundary = 'reflect')
    #    fluxivar_sm =  djs_median(fluxivar, width = 5, boundary = 'reflect')
    fluxivar_sm = fluxivar_sm*(fluxivar > 0.0)

    indsp = (wave > wvmnx[0]) & (wave < wvmnx[1]) & \
             np.isfinite(flux_sm) & (flux_sm < 5.0e5) &  \
             (flux_sm > -1000.0) & (fluxivar_sm > 0.0)


    b_answer, bmask   = bspline_iterfit(wave[indsp], flux_sm[indsp], invvar = fluxivar_sm[indsp],kwargs_bspline={'everyn': 1.5}, kwargs_reject={'groupbadpix':True,'maxrej':1})
    b_answer, bmask2  = bspline_iterfit(wave[indsp], flux_sm[indsp], invvar = fluxivar_sm[indsp]*bmask, kwargs_bspline={'everyn': 1.5}, kwargs_reject={'groupbadpix':True,'maxrej':1})
    c_answer, cmask   = bspline_iterfit(wave[indsp], flux_sm[indsp], invvar = fluxivar_sm[indsp]*bmask2,kwargs_bspline={'everyn': 30}, kwargs_reject={'groupbadpix':True,'maxrej':1})
    spline_flux, _ = b_answer.value(wave[indsp])
    cont_flux, _ = c_answer.value(wave[indsp])

    sn2 = (np.fmax(spline_flux*(np.sqrt(np.fmax(fluxivar_sm[indsp], 0))*bmask2),0))**2
    ind_nonzero = (sn2 > 0)
    nonzero = np.sum(ind_nonzero)
    if(nonzero >0):
        (mean, med_sn2, stddev) = sigma_clipped_stats(sn2,sigma_lower=3.0,sigma_upper=5.0)
    else: med_sn2 = 0.0
    sn2_med = median_filter(sn2, size=9, mode='reflect')
    #sn2_med = djs_median(sn2, width = 9, boundary = 'reflect')
    igood = (ivar > 0.0)
    ngd = np.sum(igood)
    if(ngd > 0):
        isrt = np.argsort(wave[indsp])
        sn2_interp = interp1d((wave[indsp])[isrt],sn2_med[isrt],assume_sorted=False, bounds_error=False,fill_value = 'extrapolate')
        sn2_sub[igood] = sn2_interp(sub_wave[igood])
    msgs.info('sqrt(med(S/N)^2) = ' + "{:5.2f}".format(np.sqrt(med_sn2)))

    min_wave = np.min(wave[indsp])
    max_wave = np.max(wave[indsp])
    spline_flux1 = np.zeros(nspec)
    cont_flux1 = np.zeros(nspec)
    sn2_1 = np.zeros(nspec)
    ispline = (wave >= min_wave) & (wave <= max_wave)
    spline_tmp, _ = b_answer.value(wave[ispline])
    spline_flux1[ispline] = spline_tmp
    cont_tmp, _ = c_answer.value(wave[ispline])
    cont_flux1[ispline] = cont_tmp
    s2_1_interp = interp1d((wave[indsp])[isrt], sn2[isrt],assume_sorted=False, bounds_error=False,fill_value = 'extrapolate')
    sn2_1[ispline] = s2_1_interp(wave[ispline])
    bmask = np.zeros(nspec,dtype='bool')
    bmask[indsp] = bmask2
    spline_flux1 = djs_maskinterp(spline_flux1,(bmask == False))
    cmask2 = np.zeros(nspec,dtype='bool')
    cmask2[indsp] = cmask
    cont_flux1 = djs_maskinterp(cont_flux1,(cmask2 == False))

    (_, _, sigma1) = sigma_clipped_stats(flux[indsp],sigma_lower=3.0,sigma_upper=5.0)

    if(med_sn2 <= 2.0):
        spline_sub[igood]= np.fmax(sigma1,0)
    else:
        if((med_sn2 <=5.0) and (med_sn2 > 2.0)):
            spline_flux1 = cont_flux1
        # Interp over points <= 0 in boxcar flux or masked points using cont model
        badpix = (spline_flux1 <= 0.5) | (bmask == False)
        goodval = (cont_flux1 > 0.0) & (cont_flux1 < 5e5)
        indbad1 = badpix & goodval
        nbad1 = np.sum(indbad1)
        if(nbad1 > 0):
            spline_flux1[indbad1] = cont_flux1[indbad1]
        indbad2 = badpix & ~goodval
        nbad2 = np.sum(indbad2)
        ngood0 = np.sum(~badpix)
        if((nbad2 > 0) or (ngood0 > 0)):
            spline_flux1[indbad2] = np.median(spline_flux1[~badpix])
        # take a 5-pixel median to filter out some hot pixels
        spline_flux1 = median_filter(spline_flux1,size=5,mode ='reflect')
        # Create the normalized object image
        if(ngd > 0):
            isrt = np.argsort(wave)
            spline_sub_interp = interp1d(wave[isrt],spline_flux1[isrt],assume_sorted=False, bounds_error=False,fill_value = 'extrapolate')
            spline_sub[igood] = spline_sub_interp(sub_wave[igood])
        else:
            spline_sub[igood] = np.fmax(sigma1, 0)

    norm_obj = (spline_sub != 0.0)*sub_obj/(spline_sub + (spline_sub == 0.0))
    norm_ivar = sub_ivar*spline_sub**2

    # Cap very large inverse variances
    ivar_mask = (norm_obj > -0.2) & (norm_obj < 0.7) & (sub_ivar > 0.0) & np.isfinite(norm_obj) & np.isfinite(norm_ivar)
    norm_ivar = norm_ivar*ivar_mask
    good = (norm_ivar.flatten() > 0.0)
    ngood = np.sum(good)


    xtemp = (np.cumsum(np.outer(4.0 + np.sqrt(np.fmax(sn2_1, 0.0)),np.ones(nspat)))).reshape((nspec,nspat))
    xtemp = xtemp/xtemp.max()


    # norm_x is the x position along the image centered on the object  trace
    norm_x = np.outer(np.ones(nspec), sub_x) - np.outer(sub_trace,np.ones(nspat))

    sigma = np.full(nspec, thisfwhm/2.3548)
    fwhmfit = sigma*2.3548
    trace_corr = np.zeros(nspec)

    # If we have too few pixels to fit a profile or S/N is too low, just use a Gaussian profile
    # TODO Clean up the logic below. It is formally correct but
    # redundant since no trace correction has been created or applied yet.  I'm only postponing doing it
    # to preserve this syntax for later when it is needed
    if((ngood < 10) or (med_sn2 < SN_GAUSS**2) or (GAUSS is True)):
        msgs.info("Too few good pixels or S/N <" + "{:5.1f}".format(SN_GAUSS) + " or GAUSS flag set")
        msgs.info("Returning Gaussian profile")
        sigma_x = norm_x/(np.outer(sigma, np.ones(nspat)) - np.outer(trace_corr,np.ones(nspat)))
        profile_model = np.exp(-0.5*sigma_x**2)/np.sqrt(2.0*np.pi)*(sigma_x**2 < 25.)
        msgs.info("FWHM="  + "{:6.2f}".format(thisfwhm) + ", S/N=" + "{:8.3f}".format(np.sqrt(med_sn2)))
        nxinf = np.sum(np.isfinite(xnew) == False)
        if(nxinf != 0):
            msgs.warn("Nan pixel values in trace correction")
            msgs.warn("Returning original trace....")
            xnew = trace_in
        inf = np.isfinite(profile_model) == False
        ninf = np.sum(inf)
        if (ninf != 0):
            msgs.warn("Nan pixel values in object profile... setting them to zero")
            profile_model[inf] = 0.0
        # Normalize profile
        norm = np.outer(np.sum(profile_model,1),np.ones(nspat))
        if(np.sum(norm) > 0.0):
            profile_model = profile_model/norm
        if ngood > 0:
            title_string = ' '
            indx = good
        else:
            title_string = 'No good pixels, showing all'
            indx = None

        fit_profile_qa(sigma_x, norm_obj, profile_model, title = title_string, ind=indx, xtrunc= 7.0)
        return (profile_model, xnew, fwhmfit, med_sn2)


    msgs.info("Gaussian vs b-spline of width " + "{:6.2f}".format(thisfwhm) + " pixels")
    area = 1.0
    sigma_x = norm_x / (np.outer(sigma, np.ones(nspat)) - np.outer(trace_corr, np.ones(nspat)))

    mask = np.full(nspec*nspat, False, dtype=bool)

    # The following lines set the limits for the b-spline fit
    limit = erfcinv(0.1/np.sqrt(med_sn2))*np.sqrt(2.0)
    if(PROF_NSIGMA is None):
        sinh_space = 0.25*np.log10(np.fmax((1000./np.sqrt(med_sn2)),10.))
        abs_sigma = np.fmin((np.abs(sigma_x.flat[good])).max(),2.0*limit)
        min_sigma = np.fmax(sigma_x.flat[good].min(), (-abs_sigma))
        max_sigma = np.fmin(sigma_x.flat[good].max(), (abs_sigma))
        nb = (np.arcsinh(abs_sigma)/sinh_space).astype(int) + 1
    else:
        msgs.info("Using PROF_NSIGMA= " + "{:6.2f}".format(PROF_NSIGMA) + " for extended/bright objects")
        nb = np.round(PROF_NSIGMA > 10)
        max_sigma = PROF_NSIGMA
        min_sigma = -1*PROF_NSIGMA
        sinh_space = np.arcsinh(PROF_NSIGMA)/nb

    rb = np.sinh((np.arange(nb) + 0.5) * sinh_space)
    bkpt = np.concatenate([(-rb)[::-1], rb])
    keep = ((bkpt >= min_sigma) & (bkpt <= max_sigma))
    bkpt = bkpt[keep]

    # Attempt B-spline first
    GOOD_PIX = (sn2_sub > SN_GAUSS**2) & (norm_ivar > 0)
    IN_PIX   = (sigma_x >= min_sigma) & (sigma_x <= max_sigma) & (norm_ivar > 0)
    ngoodpix = np.sum(GOOD_PIX)
    ninpix     = np.sum(IN_PIX)

    if (ngoodpix >= 0.2*ninpix):
        inside,  = np.where((GOOD_PIX & IN_PIX).flatten())
    else:
        inside, = np.where(IN_PIX.flatten())


    si = inside[np.argsort(sigma_x.flat[inside])]
    sr = si[::-1]

    bset, bmask = bspline_iterfit(sigma_x.flat[si],norm_obj.flat[si], invvar = norm_ivar.flat[si]
                           , nord = 4, bkpt = bkpt, maxiter = 15, upper = 1, lower = 1)
    mode_fit, _ = bset.value(sigma_x.flat[si])
    median_fit = np.median(norm_obj[norm_ivar > 0.0])

    # TODO I don't follow the logic behind this statement but I'm leaving it for now. If the median is large it is used, otherwise we  user zero???
    if (np.abs(median_fit) > 0.01):
        msgs.info("Median flux level in profile is not zero: median = " + "{:7.4f}".format(median_fit))
    else:
        median_fit = 0.0

    # Find the peak and FWHM based this profile fit
    (peak, peak_x, lwhm, rwhm) = findfwhm(mode_fit - median_fit, sigma_x.flat[si])
    trace_corr = np.full(nspec, peak_x)
    min_level = peak*np.exp(-0.5*limit**2)

    bspline_fwhm = (rwhm - lwhm)*thisfwhm/2.3548
    msgs.info("Bspline FWHM: " + "{:7.4f}".format(bspline_fwhm) + ", compared to initial object finding FWHM: " + "{:7.4f}".format(thisfwhm) )
    sigma = sigma * (rwhm-lwhm)/2.3548

    limit = limit * (rwhm-lwhm)/2.3548

    rev_fit = mode_fit[::-1]
    lind, = np.where(((rev_fit < (min_level+median_fit)) & (sigma_x.flat[sr] < peak_x)) | (sigma_x.flat[sr] < (peak_x-limit)))
    if (lind.size > 0):
        lp = lind.min()
        l_limit = sigma_x.flat[sr[lp]]
    else:
        l_limit = min_sigma

    rind, = np.where(((mode_fit < (min_level+median_fit)) & (sigma_x.flat[si] > peak_x)) | (sigma_x.flat[si] > (peak_x+limit)))
    if (rind.size > 0):
        rp = rind.min()
        r_limit = sigma_x.flat[si[rp]]
    else:
        r_limit = max_sigma

    msgs.info("Trace limits: limit = " + "{:7.4f}".format(limit) + ", min_level = " + "{:7.4f}".format(min_level) +
              ", l_limit = " + "{:7.4f}".format(l_limit) + ", r_limit = " + "{:7.4f}".format(r_limit))

    # Just grab the data points within the limits
    mask[si]=((norm_ivar.flat[si] > 0) & (np.abs(norm_obj.flat[si] - mode_fit) < 0.1))
    inside, = np.where((sigma_x.flat[si] > l_limit) & (sigma_x.flat[si] < r_limit) & mask[si])
    ninside = inside.size


    # If we have too few pixels after this step, then again just use a Gaussian profile and return. Note that
    # we are following the original IDL code here and not using the improved sigma and trace correction for the
    # profile at this stage since ninside is so small.
    if(ninside < 10):
        msgs.info("Too few pixels inside l_limit and r_limit")
        msgs.info("Returning Gaussian profile")
        profile_model = np.exp(-0.5*sigma_x**2)/np.sqrt(2.0*np.pi)*(sigma_x**2 < 25.)
        msgs.info("FWHM="  + "{:6.2f}".format(thisfwhm) + ", S/N=" + "{:8.3f}".format(np.sqrt(med_sn2)))
        nxinf = np.sum(np.isfinite(xnew) == False)
        if(nxinf != 0):
            msgs.warn("Nan pixel values in trace correction")
            msgs.warn("Returning original trace....")
            xnew = trace_in
        inf = np.isfinite(profile_model) == False
        ninf = np.sum(inf)
        if (ninf != 0):
            msgs.warn("Nan pixel values in object profile... setting them to zero")
            profile_model[inf] = 0.0
        # Normalize profile
        norm = np.outer(np.sum(profile_model,1),np.ones(nspat))
        if(np.sum(norm) > 0.0):
            profile_model = profile_model/norm

        fit_profile_qa(sigma_x, norm_obj, profile_model, l_limit = l_limit, r_limit = r_limit, ind =good, xlim = 7.0)
        return (profile_model, xnew, fwhmfit, med_sn2)

    sigma_iter = 3
    isort =  (xtemp.flat[si[inside]]).argsort()
    inside = si[inside[isort]]
    pb =np.ones(inside.size)

    # ADD the loop here later
    for iiter in range(1,sigma_iter + 1):
        mode_zero, _ = bset.value(sigma_x.flat[inside])
        mode_zero = mode_zero*pb

        mode_min05, _ = bset.value(sigma_x.flat[inside]-0.5)
        mode_plu05, _ = bset.value(sigma_x.flat[inside]+0.5)
        mode_shift = (mode_min05  - mode_plu05)*pb*((sigma_x.flat[inside] > (l_limit + 0.5)) &
                                                (sigma_x.flat[inside] < (r_limit - 0.5)))

        mode_by13, _ = bset.value(sigma_x.flat[inside]/1.3)
        mode_stretch = mode_by13*pb/1.3 - mode_zero

        nbkpts = (np.log10(np.fmax(med_sn2, 11.0))).astype(int)

        xx = np.sum(xtemp, 1)/nspat
        profile_basis = np.column_stack((mode_zero,mode_shift))

        mode_shift_out = bspline_profile(xtemp.flat[inside], norm_obj.flat[inside], norm_ivar.flat[inside], profile_basis
                                      ,maxiter=1,kwargs_bspline= {'nbkpts':nbkpts})
        mode_shift_set = mode_shift_out[0]
        temp_set = bspline(None, fullbkpt = mode_shift_set.breakpoints,nord=mode_shift_set.nord)
        temp_set.coeff = mode_shift_set.coeff[0, :]
        h0, _ = temp_set.value(xx)
        temp_set.coeff = mode_shift_set.coeff[1, :]
        h1, _ = temp_set.value(xx)
        ratio_10 = (h1/(h0 + (h0 == 0.0)))
        delta_trace_corr = ratio_10/(1.0 + np.abs(ratio_10)/0.1)
        trace_corr = trace_corr + delta_trace_corr

        profile_basis = np.column_stack((mode_zero,mode_stretch))
        mode_stretch_out = bspline_profile(xtemp.flat[inside], norm_obj.flat[inside], norm_ivar.flat[inside], profile_basis,
                                            maxiter=1,fullbkpt = mode_shift_set.breakpoints)
        mode_stretch_set = mode_stretch_out[0]
        temp_set = bspline(None, fullbkpt = mode_stretch_set.breakpoints,nord=mode_stretch_set.nord)
        temp_set.coeff = mode_stretch_set.coeff[0, :]
        h0, _ = temp_set.value(xx)
        temp_set.coeff = mode_stretch_set.coeff[1, :]
        h2, _ = temp_set.value(xx)
        h0 = np.fmax(h0 + h2*mode_stretch.sum()/mode_zero.sum(),0.1)
        ratio_20 = (h2 / (h0 + (h0 == 0.0)))
        sigma_factor = 0.3 * ratio_20 / (1.0 + np.abs(ratio_20))

        msgs.info("Iteration# " + "{:3d}".format(iiter))
        msgs.info("Median abs value of trace correction = " + "{:8.3f}".format(np.median(np.abs(delta_trace_corr))))
        msgs.info("Median abs value of width correction = " + "{:8.3f}".format(np.median(np.abs(sigma_factor))))

        sigma = sigma*(1.0 + sigma_factor)
        area = area * h0/(1.0 + sigma_factor)

        sigma_x = norm_x / (np.outer(sigma, np.ones(nspat)) - np.outer(trace_corr, np.ones(nspat)))

        # Update the profile B-spline fit for the next iteration
        if iiter < sigma_iter-1:
            ss = sigma_x.flat[inside].argsort()
            pb = (np.outer(area, np.ones(nspat,dtype=float))).flat[inside]
            keep = (bkpt >= sigma_x.flat[inside].min()) & (bkpt <= sigma_x.flat[inside].max())
            if keep.sum() == 0:
                keep = np.ones(bkpt.size, type=bool)
            bset_out = bspline_profile(sigma_x.flat[inside[ss]],norm_obj.flat[inside[ss]],norm_ivar.flat[inside[ss]],pb[ss],
                                    nord = 4, bkpt=bkpt[keep],maxiter=2)
            bset = bset_out[0] # This updated bset used for the next set of trace corrections

    # Apply trace corrections only if they are small (added by JFH)
    if np.median(np.abs(trace_corr*sigma)) < MAX_TRACE_CORR:
        xnew = trace_corr * sigma + trace_in
    else:
        xnew = trace_in

    fwhmfit = sigma*2.3548
    ss=sigma_x.flatten().argsort()
    inside, = np.where((sigma_x.flat[ss] >= min_sigma) &
                       (sigma_x.flat[ss] <= max_sigma) &
                       mask[ss] &
                       np.isfinite(norm_obj.flat[ss]) &
                       np.isfinite(norm_ivar.flat[ss]))
    pb = (np.outer(area, np.ones(nspat,dtype=float)))
    bset_out = bspline_profile(sigma_x.flat[ss[inside]],norm_obj.flat[ss[inside]], norm_ivar.flat[ss[inside]], pb.flat[ss[inside]],
                            nord=4, bkpt = bkpt, upper = 10, lower=10)
    bset = bset_out[0]
    outmask = bset_out[1]

    # inmask = False for pixels within (min_sigma, max_sigma), True outside
    inmask = (sigma_x.flatten() > min_sigma) & (sigma_x.flatten() < max_sigma)
    full_bsp = np.zeros(nspec*nspat, dtype=float)
    sigma_x_inmask = sigma_x.flat[inmask]
    yfit_out, _  = bset.value(sigma_x_inmask)
    full_bsp[inmask] = yfit_out
    isrt = sigma_x_inmask.argsort()
    (peak, peak_x, lwhm, rwhm) = findfwhm(yfit_out[isrt] - median_fit, sigma_x_inmask[isrt])


    left_bool = (((full_bsp[ss] < (min_level+median_fit)) & (sigma_x.flat[ss] < peak_x)) | (sigma_x.flat[ss] < (peak_x-limit)))[::-1]
    ind_left, = np.where(left_bool)
    lp = np.fmax(ind_left.min(), 0)
    righ_bool = ((full_bsp[ss] < (min_level+median_fit)) & (sigma_x.flat[ss] > peak_x))  | (sigma_x.flat[ss] > (peak_x+limit))
    ind_righ, = np.where(righ_bool)
    rp = np.fmax(ind_righ.min(), 0)
    l_limit = ((sigma_x.flat[ss])[::-1])[lp] - 0.1
    r_limit = sigma_x.flat[ss[rp]] + 0.1

    while True:
        l_limit += 0.1
        l_fit, _ = bset.value(np.asarray([l_limit]))
        l2, _ = bset.value(np.asarray([l_limit])* 0.9)
        l_deriv = (np.log(l2[0]) - np.log(l_fit[0]))/(0.1*l_limit)
        if (l_deriv < -1.0) | (l_limit >= -1.0):
            break

    while True:
        r_limit -= 0.1
        r_fit, _ = bset.value(np.asarray([r_limit]))
        r2, _ = bset.value(np.asarray([r_limit])* 0.9)
        r_deriv = (np.log(r2[0]) - np.log(r_fit[0]))/(0.1*r_limit)
        if (r_deriv > 1.0) | (r_limit <= 1.0):
            break


    # JXP kludge
    if PROF_NSIGMA is not None:
       #By setting them to zero we ensure QA won't plot them in the profile QA.
       l_limit = 0.0
       r_limit = 0.0


    # Hack to fix degenerate profiles which have a positive derivative
    if (l_deriv < 0) and (r_deriv > 0) and NO_DERIV is False:
        left = sigma_x.flatten() < l_limit
        full_bsp[left] =  np.exp(-(sigma_x.flat[left]-l_limit)*l_deriv) * l_fit
        right = sigma_x.flatten() > r_limit
        full_bsp[right] = np.exp(-(sigma_x.flat[right] - r_limit) * r_deriv) * r_fit

    # Final object profile
    full_bsp = full_bsp.reshape(nspec,nspat)
    profile_model = full_bsp*pb
    res_mode = (norm_obj.flat[ss[inside]] - profile_model.flat[ss[inside]])*np.sqrt(norm_ivar.flat[ss[inside]])
    chi_good = (outmask == True) & (norm_ivar.flat[ss[inside]] > 0)
    chi_med = np.median(res_mode[chi_good]**2)
    chi_zero = np.median(norm_obj.flat[ss[inside]]**2*norm_ivar.flat[ss[inside]])

    msgs.info("----------  Results of Profile Fit ----------")
    msgs.info(" min(fwhmfit)={:5.2f}".format(fwhmfit.min()) +
              " max(fwhmfit)={:5.2f}".format(fwhmfit.max()) + " median(chi)={:5.2f}".format(chi_med) +
              " nbkpts={:2d}".format(bkpt.size))

    nxinf = np.sum(np.isfinite(xnew) == False)
    if (nxinf != 0):
        msgs.warn("Nan pixel values in trace correction")
        msgs.warn("Returning original trace....")
        xnew = trace_in
    inf = np.isfinite(profile_model) == False
    ninf = np.sum(inf)
    if (ninf != 0):
        msgs.warn("Nan pixel values in object profile... setting them to zero")
        profile_model[inf] = 0.0
    # Normalize profile
    norm = np.outer(np.sum(profile_model, 1), np.ones(nspat))
    if (np.sum(norm) > 0.0):
        profile_model = profile_model / norm
    msgs.info("FWHM="  + "{:6.2f}".format(thisfwhm) + ", S/N=" + "{:8.3f}".format(np.sqrt(med_sn2)))
    fit_profile_qa(sigma_x, norm_obj/(pb + (pb == 0.0)), full_bsp, l_limit = l_limit, r_limit = r_limit, ind = ss[inside], xlim = PROF_NSIGMA)

    return (profile_model, xnew, fwhmfit, med_sn2)



def parse_hand_dict(HAND_DICT):
    """ Utility routine for objfind to parase the HAND_DICT dictionary for hand selected apertures

    Parameters
    ----------
    HAND_DICT:   dictionary

    Returns
    -------
    hand_spec:  spectral pixel location, numpy float 1-d array with size equal to number of hand aperatures requested
    hand_spat:  spatial pixel location, numpy float 1-d array with size equal to number of hand aperatures requested
    hand_fwhm:  hand aperture fwhm, numpy float 1-d array with size equal to number of hand aperatures requested

    Revision History
    ----------------
    23-June-2018  Written by J. Hennawi
    """


    if ('HAND_SPEC' not in HAND_DICT.keys() | 'HAND_SPAT' not in HAND_DICT.keys()):
        raise ValueError('HAND_SPEC and HAND_SPAT must be set in the HAND_DICT')

    HAND_SPEC=np.asarray(HAND_DICT['HAND_SPEC'])
    HAND_SPAT=np.asarray(HAND_DICT['HAND_SPAT'])
    HAND_DET = np.asarray(HAND_DICT['HAND_DET'])
    if(HAND_SPEC.size == HAND_SPAT.size == HAND_DET.size) == False:
        raise ValueError('HAND_SPEC, HAND_SPAT, and HAND_DET must have the same size in the HAND_DICT')
    nhand = HAND_SPEC.size

    HAND_FWHM = HAND_DICT.get('HAND_FWHM')
    if HAND_FWHM is not None:
        HAND_FWHM = np.asarray(HAND_FWHM)
        if(HAND_FWHM.size==HAND_SPEC.size):
            pass
        elif (HAND_FWHM.size == 1):
            HAND_FWHM = np.full(nhand, HAND_FWHM)
        else:
            raise ValueError('HAND_FWHM must either be a number of have the same size as HAND_SPEC and HAND_SPAT')
    else:
        HAND_FWHM = np.full(nhand, None)

    return (HAND_SPEC, HAND_SPAT, HAND_DET, HAND_FWHM)



specobj_dict = {'config': None, 'slitid': None, 'scidx': 1, 'det': 1, 'objtype': 'science'}



def objfind(image, invvar, slit_left, slit_righ, mask = None, FWHM = 3.0,
            HAND_DICT = None, std_trace = None, ncoeff = 5, nperslit = 10,  BG_SMTH = 5.0, PKWDTH = 3.0,
            SIG_THRESH = 5.0, PEAK_THRESH = 0.0, ABS_THRESH = 0.0, TRIM_EDG = (3,3), OBJMASK_NTHRESH = 2.0,
            SHOW_TRACE = False, SHOW_FITS = False, SHOW_PEAKS = True, specobj_dict=specobj_dict):

    """ DOCS COMING SOON

    Parameters
    ----------

    Returns
    -------

    Revision History
    ----------------
    10-Mar-2005  First version written by D. Schlegel, LBL
    2005-2018    Improved by J. F. Hennawi and J. X. Prochaska
    23-June-2018 Ported to python by J. F. Hennawi and significantly improved
    """

    from pypeit.utils import find_nminima
    from pypeit.core.trace_slits import trace_fweight, trace_gweight
    from pypeit import specobjs
    import scipy

    # Check that PEAK_THRESH values make sense
    if ((PEAK_THRESH >=0.0) & (PEAK_THRESH <=1.0)) == False:
        msgs.error('Invalid value of PEAK_THRESH. It must be between 0.0 and 1.0')

    frameshape = image.shape
    nspec = frameshape[0]
    nspat = frameshape[1]
    specmid = nspec//2

    # Some information about this slit we need for later when we instantiate specobj objects
    spec_vec = np.arange(nspec)
    spat_vec = np.arange(nspat)
    slit_spec_pos = nspec/2.0

    slit_spat_pos = (np.interp(slit_spec_pos, spec_vec, slit_left), np.interp(slit_spec_pos, spec_vec, slit_righ))

    # Synthesize thismask, ximg, and edgmask  from slit boundaries. Doing this outside this
    # routine would save time. But this is pretty fast, so we just do it here to make the interface simpler.
    pad =0
    slitpix = pixels.slit_pixels(slit_left, slit_righ, frameshape, pad)
    thismask = (slitpix > 0)

#    if (ximg is None) | (edgmask is None):
    ximg, edgmask = pixels.ximg_and_edgemask(slit_left, slit_righ, thismask, trim_edg = TRIM_EDG)

    # If a mask was not passed in, create it
    if mask is None:
        mask = thismask & (invvar > 0.0)


    thisimg =image*((thismask == True) & (mask == True) & (edgmask == False))
    #  Smash the image (for this slit) into a single flux vector.  How many pixels wide is the slit at each Y?
    xsize = slit_righ - slit_left
    nsamp = np.ceil(np.median(xsize))
    # Mask skypixels with 2 FWHM of edge
    left_asym = np.outer(slit_left,np.ones(int(nsamp))) + np.outer(xsize/nsamp, np.arange(nsamp))
    righ_asym = left_asym + np.outer(xsize/nsamp, np.ones(int(nsamp)))
    # This extract_asymbox2 call smashes the image in the spectral direction along the curved object traces
    flux_spec = extract_asymbox2(thisimg, left_asym, righ_asym)
    flux_mean, flux_median, flux_sig = sigma_clipped_stats(flux_spec,axis=0, sigma = 4.0)
    if (nsamp < 9.0*FWHM):
        fluxsub = flux_mean.data - np.median(flux_mean.data)
    else:
        kernel_size= int(np.ceil(BG_SMTH*FWHM) // 2 * 2 + 1) # This ensure kernel_size is odd
        fluxsub = flux_mean.data - scipy.signal.medfilt(flux_mean.data, kernel_size=kernel_size)
        # This little bit below deals with degenerate cases for which the slit gets brighter toward the edge, i.e. when
        # alignment stars saturate and bleed over into other slits. In this case the median smoothed profile is the nearly
        # everywhere the same as the profile itself, and fluxsub is full of zeros (bad!). If 90% or more of fluxsub is zero,
        # default to use the unfiltered case
        isub_bad = (fluxsub == 0.0)
        frac_bad = np.sum(isub_bad)/nsamp
        if frac_bad > 0.9:
            fluxsub = flux_mean.data - np.median(flux_mean.data)

    fluxconv = scipy.ndimage.filters.gaussian_filter1d(fluxsub, FWHM/2.3548,mode='nearest')

    xcen, sigma, ledg, redg = find_nminima(-fluxconv,nfind=nperslit, width = PKWDTH, minsep = np.fmax(FWHM, PKWDTH))
    ypeak = np.interp(xcen,np.arange(nsamp),fluxconv)
    # Create a mask for pixels to use for a background flucutation level estimate. Mask spatial pixels that hit an object
    imask = np.ones(int(nsamp), dtype=bool)
    xvec = np.arange(nsamp)
    for zz in range(len(xcen)):
        ibad = (np.abs(xvec - xcen[zz]) <= 2.0*FWHM)
        imask[ibad] = False

    # Good pixels for flucutation level estimate. Omit edge pixels and pixels within a FWHM of a candidate object
    igd = imask & (xvec > 3.0) & (xvec <= (nsamp-3.0))
    if np.any(igd) == False:
        igd = np.ones(int(nsamp),dtype=bool) # if all pixels are masked for some reason, don't mask

    (mean, med_sn2, skythresh) = sigma_clipped_stats(fluxconv[igd], sigma=1.5)
    (mean, med_sn2, sigma)     = sigma_clipped_stats(fluxconv[igd], sigma=2.5)
    if(skythresh == 0.0) & (sigma != 0.0):
        skythresh = sigma
    elif(skythresh == 0.0) & (sigma==0.0):  # if both SKYTHRESH and sigma are zero mask out the zero pixels and reavaluate
        good = fluxconv > 0.0
        if np.any(good) == True:
            (mean, med_sn2, skythresh) = sigma_clipped_stats(fluxconv[good], sigma=1.5)
            (mean, med_sn2, sigma) = sigma_clipped_stats(fluxconv[good], sigma=2.5)
        else:
            msgs.error('Object finding failed. All the elements of the fluxconv spatial profile array are zero')
    else:
        pass

    # Get rid of peaks within TRIM_EDG of slit edge which are almost always spurious, this should have been handled
    # with the edgemask, but we do it here anyway
    not_near_edge = (xcen > TRIM_EDG[0]) & (xcen < (nsamp - TRIM_EDG[1]))
    if np.any(~not_near_edge):
        msgs.warn('Discarding {:d}'.format(np.sum(~not_near_edge)) + ' at spatial pixels spat = {:}'.format(xcen[~not_near_edge]) +
                  ' which land within TRIM_EDG = {:5.2f}'.format(TRIM_EDG) +
                  ' pixels from the slit boundary for this nsamp = {:5.2f}'.format(nsamp) + ' wide slit')
        msgs.warn('You must decrease from the current value of TRIM_EDG in order to keep them')
        msgs.warn('Such edge objects are often spurious')

    xcen = xcen[not_near_edge]
    ypeak = ypeak[not_near_edge]
    npeak = len(xcen)

    # Instantiate a null specobj
    sobjs = specobjs.SpecObjs()
    # Choose which ones to keep and discard based on threshold params. Create SpecObj objects
    if npeak > 0:
        # Possible thresholds    [significance,  fraction of brightest, absolute]
        threshvec = np.array([SIG_THRESH*sigma, PEAK_THRESH*ypeak.max(), ABS_THRESH])
        threshold = threshvec.max()
        msgs.info('Using object finding threshold of: {:5.2f}'.format(threshold))
        # Trim to only objects above this threshold
        ikeep = (ypeak >= threshold)
        xcen = xcen[ikeep]
        ypeak = ypeak[ikeep]
        nobj_reg = len(xcen)
        # Now create SpecObj objects for all of these
        for iobj in range(nobj_reg):
            # ToDo Label with objid and objind here?
            thisobj = specobjs.SpecObj(frameshape, slit_spat_pos, slit_spec_pos, det = specobj_dict['det'],
                              config = specobj_dict['config'], slitid = specobj_dict['slitid'],
                              scidx = specobj_dict['scidx'], objtype=specobj_dict['objtype'])
            thisobj.spat_fracpos = xcen[iobj]/nsamp
            thisobj.smash_peakflux = ypeak[iobj]
            sobjs.add_sobj(thisobj)
    else:
        nobj_reg = 0


    if SHOW_PEAKS:
        plt.plot(np.arange(nsamp), fluxsub, color ='cornflowerblue',linestyle=':', label='Collapsed Slit profile')
        plt.plot(np.arange(nsamp), fluxconv, color='black', label = 'FWHM Convolved Profile')
        plt.plot(xcen, ypeak, color='red', marker='o', markersize=10.0, mfc='lawngreen', fillstyle='full',
                 linestyle='None', zorder = 10,label='Object Found')
        plt.legend()
        plt.show()


    # Now loop over all the regular apertures and assign preliminary traces to them.
    for iobj in range(nobj_reg):
        # Was a standard trace provided? If so, use that as a crutch.
        if std_trace is not None:
            msgs.info('Using input STANDARD star trace as crutch for object tracing'.format(threshold))
            x_trace = np.interp(specmid, spec_vec, std_trace)
            shift = slit_left + xsize*sobjs[iobj].spat_fracpos - x_trace
            sobjs[iobj].trace_spat = std_trace + shift
        else:    # If no standard is provided shift left slit boundary over to be initial trace
            # ToDO make this the average left and right boundary instead. That would be more robust.
            sobjs[iobj].trace_spat = slit_left  + xsize*sobjs[iobj].spat_fracpos

        sobjs[iobj].spat_pixpos = sobjs[iobj].trace_spat[specmid]
        # Set the idx for any prelminary outputs we print out. These will be updated shortly
        sobjs[iobj].set_idx()

        # Determine the FWHM max
        yhalf = 0.5*sobjs[iobj].smash_peakflux
        xpk = sobjs[iobj].spat_fracpos*nsamp
        x0 = int(np.rint(xpk))
        # TODO It seems we have two codes that do similar things, i.e. findfwhm in arextract.py. Could imagine having one
        # Find right location where smash profile croses yhalf
        if x0 < (int(nsamp)-1):
            ind_righ, = np.where(fluxconv[x0:] < yhalf)
            if len(ind_righ) > 0:
                i2 = ind_righ[0]
                if i2 == 0:
                    xrigh = None
                else:
                    xrigh_int = scipy.interpolate.interp1d(fluxconv[x0 + i2-1:x0 + i2 + 1], x0 + np.array([i2-1,i2],dtype=float),assume_sorted=False)
                    xrigh = xrigh_int([yhalf])[0]
            else:
                xrigh = None
        else:
            xrigh = None
        # Find left location where smash profile crosses yhalf
        if x0 > 0:
            ind_left, = np.where(fluxconv[0:np.fmin(x0+1,int(nsamp)-1)] < yhalf)
            if len(ind_left) > 0:
                i1 = (ind_left[::-1])[0]
                if i1 == (int(nsamp)-1):
                    xleft = None
                else:
                    xleft_int = scipy.interpolate.interp1d(fluxconv[i1:i1+2],np.array([i1,i1+1],dtype=float), assume_sorted= False)
                    xleft = xleft_int([yhalf])[0]
            else:
                xleft = None
        else:
            xleft = None

        if (xleft is None) & (xrigh is None):
            fwhm_measure = None
        elif xrigh is None:
            fwhm_measure = 2.0*(xpk- xleft)
        elif xleft is None:
            fwhm_measure = 2.0*(xrigh - xpk)
        else:
            fwhm_measure = (xrigh - xleft)

        if fwhm_measure is not None:
            sobjs[iobj].fwhm = np.sqrt(np.fmax(fwhm_measure**2 - FWHM**2, (FWHM/2.0)**2)) # Set a floor of FWHM/2 on FWHM
        else:
            sobjs[iobj].fwhm = FWHM


    objmask = np.zeros_like(thismask, dtype=bool)
    skymask = np.copy(thismask)
    if (len(sobjs) == 0) & (HAND_DICT == None):
        msgs.info('No objects found')
        return (None, objmask, skymask)


    msgs.info('Fitting the object traces')
    # Iterate flux weighted centroiding
    niter = 6
    fwhm_vec = np.zeros(niter)
    fwhm_vec[0:niter//3] = 1.3*FWHM
    fwhm_vec[niter//3:2*niter//3] = 1.1*FWHM
    fwhm_vec[2*niter//3:] = FWHM

    # Note the transpose is here because we
    xpos0 = sobjs.trace_spat.T
    #xpos0 = np.stack([spec.trace_spat for spec in specobjs], axis=1)
    # This xinvvar is used to handle truncated slits/orders so that they don't break the fits
    xfit1 = xpos0
    #ypos = np.outer(spec_vec, np.ones(nobj_reg))
    yind = np.arange(nspec,dtype=int)
    for iiter in range(niter):
        xpos1, xerr1 = trace_fweight(image*mask,xfit1, invvar = invvar*mask, radius = fwhm_vec[iiter])
        # Do not do any kind of masking based on xerr1. Trace fitting is much more robust when masked pixels are simply
        # replaced by the tracing crutch
        xerr1 =np.ones_like(xerr1)
        # Mask out anything that left the image. 0 = good, 1 = masked (convention from robust_polyfit)
        tracemask1 = np.zeros_like(xpos0,dtype=int)
        off_image = (xpos1 < -0.2*nspat) | (xpos1 > 1.2*nspat)
        tracemask1[off_image] = 1
        # trace_fweight returns 999 for pixels that had large offsets. Mask these explicitly
        #mask_999 = (xerr1 > 900.0)
        #tracemask[mask_999] = 1
        xind = (np.fmax(np.fmin(np.rint(xpos1),nspat-1),0)).astype(int)
        for iobj in range(nobj_reg):
          # Mask out anything that has left the slit/order.
          tracemask1[:,iobj] = tracemask1[:, iobj] | (thismask[yind, xind[:,iobj]] == False).astype(int)
          # ToDO add maxdev functionality?
          polymask, coeff_fit1 = utils.robust_polyfit(spec_vec,xpos1[:,iobj], ncoeff
                                                      , function = 'legendre',initialmask = tracemask1[:,iobj],forceimask=True)
          xfit1[:,iobj] = utils.func_val(coeff_fit1, spec_vec, 'legendre')

          # Plot all the points that were not masked initially
          if(SHOW_FITS == True) & (iiter == niter - 1):
              nomask = (tracemask1[:,iobj]==0)
              plt.errorbar(spec_vec[nomask],xpos1[nomask,iobj],yerr=xerr1[nomask,iobj], c='k',fmt='o',markersize=2.0,linestyle='None', elinewidth = 0.2, )
              plt.plot(spec_vec,xfit1[:,iobj],c='red',zorder=10,linewidth = 2.0)
              if np.any(~nomask):
                  plt.plot(spec_vec[~nomask],xfit1[~nomask,iobj], c='blue',marker='+',markersize=4.0,linestyle='None', zorder= 20)
              plt.title('Flux Weighted Centroid to object {:s}.'.format(sobjs[iobj].idx))
              plt.ylim((0.995*xfit1[:, iobj].min(), 1.005*xfit1[:, iobj].max()))
              plt.xlabel('Spectral Pixel')
              plt.ylabel('Spatial Pixel')
              plt.show()

    xfit2 = xfit1

    # Iterate Gaussian weighted centroiding
    for iiter in range(niter):
        xpos2, xerr2 = trace_gweight(image*mask,xfit2, invvar = invvar*mask, sigma = FWHM/2.3548)
        # Do not do any kind of masking based on xerr2. Trace fitting is much more robust when masked pixels are simply
        # replaced by the tracing crutch
        # Mask out anything that left the image. 0 = good, 1 = masked (convention from robust_polyfit)
        tracemask2 = np.zeros_like(xpos0,dtype=int)
        off_image = (xpos2 < -0.2*nspat) | (xpos2 > 1.2*nspat)
        tracemask2[off_image] = 1
        # trace_gweight returns 999 for pixels that had large offsets. Mask these explicitly
        #mask_999 = (xerr2 > 900.0)
        #tracemask[mask_999] = 1
        xind = (np.fmax(np.fmin(np.rint(xpos2),nspat-1),0)).astype(int)
        for iobj in range(nobj_reg):
          # Mask out anything that has left the slit/order.
          tracemask2[:,iobj] = tracemask2[:, iobj] | (thismask[yind, xind[:,iobj]] == False).astype(int)
          # ToDO add maxdev functionality?
          polymask, coeff_fit2 = utils.robust_polyfit(spec_vec,xpos2[:,iobj], ncoeff
                                                      , function = 'legendre',initialmask = tracemask2[:,iobj],forceimask=True)
          xfit2[:,iobj] = utils.func_val(coeff_fit2, spec_vec, 'legendre')
          ## Accept the last iteration of this Gaussian centroiding as the final fit. Update some other things
          if (iiter == niter-1):
              sobjs[iobj].trace_spat = xfit2[:,iobj]
              sobjs[iobj].spat_pixpos = sobjs[iobj].trace_spat[specmid]
              sobjs[iobj].set_idx()
              # Plot all the points that were not masked initially
              if(SHOW_FITS == True):
                  nomask = (tracemask2[:,iobj]==0)
                  plt.errorbar(spec_vec[nomask],xpos2[nomask,iobj],yerr=xerr2[nomask,iobj], c='k',fmt='o',markersize=2.0,linestyle='None', elinewidth = 0.2, )
                  plt.plot(spec_vec,xfit2[:,iobj],c='red',zorder=10,linewidth = 2.0)
                  if np.any(~nomask):
                      plt.plot(spec_vec[~nomask],xfit2[~nomask,iobj], c='blue',marker='+',markersize=4.0,linestyle='None', zorder= 20)
                  plt.title('Gaussian Weighted Centroid to object {:s}.'.format(sobjs[iobj].idx))
                  plt.ylim((0.995*xfit2[:,iobj].min(),1.005*xfit2[:,iobj].max()))
                  plt.xlabel('Spectral Pixel')
                  plt.ylabel('Spatial Pixel')
                  plt.show()




    # Now deal with the hand apertures if a HAND_DICT was passed in. Add these to the SpecObj objects
    if HAND_DICT is not None:
        # First Parse the hand_dict
        HAND_SPEC, HAND_SPAT, HAND_DET, HAND_FWHM = parse_hand_dict(HAND_DICT)
        # Determine if these hand apertures land on the slit in question
        hand_on_slit = thismask[int(np.rint(HAND_SPEC)),int(np.rint(HAND_SPAT))]
        HAND_SPEC = HAND_SPEC[hand_on_slit]
        HAND_SPAT = HAND_SPAT[hand_on_slit]
        HAND_DET  = HAND_DET[hand_on_slit]
        HAND_FWHM = HAND_FWHM[hand_on_slit]
        nobj_hand = len(HAND_SPEC)

        # Decide how to assign a trace to the hand objects
        if nobj_reg > 0:  # Use brightest object on slit?
            smash_peakflux = sobjs.smash_peakflux
            ibri = smash_peakflux.argmax()
            trace_model = sobjs[ibri].trace_spat
            med_fwhm_reg = np.median(sobjs.fwhm)
        elif std_trace is not None:   # If no objects found, use the standard?
            trace_model = std_trace
        else:  # If no objects or standard use the slit boundary
            trace_model = slit_left
        # Loop over HAND apertures and create and assign specobj
        for iobj in range(nobj_hand):
            thisobj = specobjs.SpecObj(frameshape, slit_spat_pos, slit_spec_pos,
                                       det=specobj_dict['det'],
                                       config=specobj_dict['config'], slitid=specobj_dict['slitid'],
                                       scidx=specobj_dict['scidx'], objtype=specobj_dict['objtype'])
            thisobj.HAND_SPEC = HAND_SPEC[iobj]
            thisobj.HAND_SPAT = HAND_SPAT[iobj]
            thisobj.HAND_DET = HAND_DET[iobj]
            thisobj.HAND_FWHM = HAND_FWHM[iobj]
            thisobj.HAND_FLAG = True
            f_ximg = scipy.interpolate.RectBivariateSpline(spec_vec, spat_vec, ximg)
            thisobj.spat_fracpos = f_ximg(thisobj.HAND_SPEC, thisobj.HAND_SPAT, grid=False) # interpolate from ximg
            thisobj.smash_peakflux = np.interp(thisobj.spat_fracpos*nsamp,np.arange(nsamp),fluxconv) # interpolate from fluxconv
            # assign the trace
            spat_0 = np.interp(thisobj.HAND_SPEC, spec_vec, trace_model)
            shift = thisobj.HAND_SPAT - spat_0
            thisobj.trace_spat = trace_model + shift
            thisobj.spat_pixpos = thisobj.trace_spat[specmid]
            thisobj.set_idx()
            if HAND_FWHM[iobj] is not None: # If a HAND_FWHM was input use that for the FWHM
                thisobj.fwhm = HAND_FWHM[iobj]
            elif nobj_reg > 0: # Otherwise is None was input, then use the median of objects on this slit if they are present
                thisobj.fwhm = med_fwhm_reg
            else:  # Otherwise just use the FWHM parameter input to the code (or the default value)
                thisobj.fwhm = FWHM
            sobjs.add_sobj(thisobj)


    nobj = len(sobjs)
    # If there are no regular aps and no hand aps, just return
    #if nobj == 0:
    #    return (None, skymask, objmask)

    ## Okay now loop over all the regular aps and exclude any which within a FWHM of the HAND_APERTURES
    if nobj_reg > 0 and HAND_DICT is not None:
        spat_pixpos = sobjs.spat_pixpos
        hand_flag = sobjs.HAND_FLAG
        spec_fwhm = sobjs.fwhm
        #spat_pixpos = np.array([spec.spat_pixpos for spec in specobjs])
        #hand_flag = np.array([spec.HAND_FLAG for spec in specobjs])
        #spec_fwhm = np.array([spec.fwhm for spec in specobjs])
        reg_ind, = np.where(hand_flag == False)
        hand_ind, = np.where(hand_flag == True)
        med_fwhm = np.median(spec_fwhm[hand_flag == False])
        spat_pixpos_hand = spat_pixpos[hand_ind]
        keep = np.ones(nobj,dtype=bool)
        for ireg in range(nobj_reg):
            close = np.abs(sobjs[reg_ind[ireg]].spat_pixpos - spat_pixpos_hand) <= 0.6*med_fwhm
            if np.any(close):
                # Print out a warning
                msgs.warn('Deleting object {:s}'.format(sobjs[reg_ind[ireg]].idx) +
                          ' because it collides with a user specified HAND aperture')
                for ihand in range(len(close)):
                    if close[ihand] == True:
                        msgs.warn('Hand aperture at (HAND_SPEC, HAND_SPAT) = ({:6.2f}'.format(sobjs[hand_ind[ihand]].HAND_SPEC) +
                                  ',{:6.2f})'.format(sobjs[hand_ind[ihand]].HAND_SPAT) +
                                  ' lands within 0.6*med_fwhm = {:4.2f}'.format(0.6*med_fwhm) + ' pixels of this object')
                keep[reg_ind[ireg]] = False

        sobjs = sobjs[keep]

    # Sort objects according to their spatial location
    nobj = len(sobjs)
    spat_pixpos = sobjs.spat_pixpos
    sobjs = sobjs[spat_pixpos.argsort()]
    # Assign integer objids
    sobjs.objid = np.arange(nobj)


    # Assign the maskwidth and compute some inputs for the object mask
    xtmp = (np.arange(nsamp) + 0.5)/nsamp
    qobj = np.zeros_like(xtmp)
    for iobj in range(nobj):
        if skythresh > 0.0:
            sobjs[iobj].maskwidth = 3.0*sobjs[iobj].fwhm*(1.0 + 0.5*np.log10(np.fmax(sobjs[iobj].smash_peakflux/skythresh,1.0)))
        else:
            sobjs[iobj].maskwidth = 3.0 * sobjs[iobj].fwhm
        sep = np.abs(xtmp-sobjs[iobj].spat_fracpos)
        sep_inc = sobjs[iobj].maskwidth/nsamp
        close = sep <= sep_inc
        qobj[close] += sobjs[iobj].smash_peakflux*np.exp(np.fmax(-2.77*(sep[close]*nsamp)**2/sobjs[iobj].fwhm**2,-9.0))

    # Create an objmask
    objmask[thismask] = np.interp(ximg[thismask],xtmp,qobj) > (OBJMASK_NTHRESH*threshold)

    # Still have to make the skymask
    all_fwhm = sobjs.fwhm
    med_fwhm = np.median(all_fwhm)
    for iobj in range(nobj):
        for ispec in range(nspec):
            spat_min = np.fmin(np.fmax(int(np.floor(sobjs[iobj].trace_spat[ispec] - med_fwhm)),0),nspat)
            spat_max = np.fmin(np.fmax(int(np.ceil(sobjs[iobj].trace_spat[ispec] + med_fwhm)),0),nspat)
            skymask[ispec,spat_min:spat_max] = False


    # If requested display the resulting traces on top of the image
    if (nobj > 0) & (SHOW_TRACE):
        viewer, ch = ginga.show_image(image*(thismask==True))
        ginga.show_slits(viewer, ch, slit_left.T, slit_righ.T, slit_ids = sobjs[0].slitid)
        for iobj in range(nobj):
            if sobjs[iobj].HAND_FLAG == False:
                color = 'green'
            else:
                color = 'orange'
            ginga.show_trace(viewer, ch,sobjs[iobj].trace_spat, trc_name = sobjs[iobj].idx, color=color)


    return (sobjs, skymask, objmask)



# This routine is deprecated, replaced by extract_boxcar
def boxcar(specobjs, sciframe, varframe, bpix, skyframe, crmask, scitrace, mswave,
           maskslits, slitpix):
    """ Perform boxcar extraction on the traced objects.
    Also perform a local sky subtraction

    Parameters
    ----------
    specobjs : list of dict
      list of SpecObj objects
    sciframe : ndarray
      science frame, should be sky subtracted
    varframe : ndarray
      variance image
    bgframe : ndarray
      sky background frame
    crmask : int ndarray
        mask of cosmic ray hits
    scitrace : list
      traces, object and background trace images

    Returns
    -------
    bgcorr : ndarray
      Correction to the sky background in the object window
    """
    # Subtract the global sky
    skysub = sciframe-skyframe

    bgfitord = 1  # Polynomial order used to fit the background
    slits = range(len(scitrace))
    nslit = len(slits)
    gdslits = np.where(~maskslits)[0]
    cr_mask = 1.0-crmask
    bgfit = np.linspace(0.0, 1.0, sciframe.shape[1])
    bgcorr = np.zeros_like(cr_mask)
    # Loop on Slits
    for sl in slits:
        if sl not in gdslits:
            continue
        word = np.where((slitpix.astype(int) == sl + 1) & (varframe > 0.))
        if word[0].size == 0:
            continue
        mask_slit = np.zeros(sciframe.shape, dtype=np.float)
        mask_slit[word] = 1.0
        # Loop on Objects
        nobj = scitrace[sl]['nobj']
        for o in range(nobj):
            msgs.info("Performing boxcar extraction of object {0:d}/{1:d} in slit {2:d}/{3:d}".format(o+1, nobj, sl+1, nslit))
            if scitrace[sl]['object'] is None:
                # The object for all slits is provided in the first extension
                objreg = np.copy(scitrace[0]['object'][:, :, o])
                wzro = np.where(slitpix != sl + 1)
                objreg[wzro] = 0.0
            else:
                objreg = scitrace[sl]['object'][:, :, o]
            # Fit the background
            msgs.info("   Fitting the background")
            if scitrace[sl]['background'] is None:
                # The background for all slits is provided in the first extension
                bckreg = np.copy(scitrace[0]['background'][:, :, o])
                wzro = np.where(slitpix != sl + 1)
                bckreg[wzro] = 0.0
            else:
                bckreg = scitrace[sl]['background'][:, :, o]
            # Trim CRs further
            bg_mask = np.zeros_like(sciframe)
            bg_mask[np.where((bckreg*cr_mask <= 0.))] = 1.
            bg_mask[np.where((slitpix != sl + 1))] = 1.
            mask_sci = np.ma.array(skysub, mask=bg_mask, fill_value=0.)
            clip_image = sigma_clip(mask_sci, axis=1, sigma=3.)  # For the mask only
            # Fit
            bgframe = func2d_fit_val(skysub, bgfitord, x=bgfit,
                                     w=(~clip_image.mask)*bckreg*cr_mask)
            # Weights
            weight = objreg*mask_slit
            sumweight = np.sum(weight, axis=1)
            # Deal with fully masked regions
            fully_masked = sumweight == 0.
            if np.any(fully_masked):
                weight[fully_masked,:] = 1.
                sumweight[fully_masked] = weight.shape[1]
            # Generate wavelength array (average over the pixels)
            wvsum = np.sum(mswave*weight, axis=1)
            wvsum /= sumweight
            # Generate sky spectrum (flux per pixel)
            skysum = np.sum(skyframe*weight, axis=1)
            skysum /= sumweight
            # Total the object flux
            msgs.info("   Summing object counts")
            scisum = np.sum((skysub-bgframe)*weight, axis=1)
            # Total the variance array
            msgs.info("   Summing variance array")
            varsum = np.sum(varframe*weight, axis=1)
            # Update background correction image
            tmp = bckreg + objreg
            gdp = np.where((tmp > 0) & (slitpix == sl + 1))
            bgcorr[gdp] = bgframe[gdp]
            # Mask
            boxmask = np.zeros(wvsum.shape, dtype=np.int)
            # Bad detector pixels
            BPs = np.sum(weight*bpix, axis=1)
            bp = BPs > 0.
            boxmask[bp] += mask_flags['bad_pix']
            # CR
            CRs = np.sum(weight*cr_mask, axis=1)
            cr = CRs > 0.
            boxmask[cr] += mask_flags['CR']
            # Fully masked
            if np.any(fully_masked):
                boxmask[fully_masked] += mask_flags['bad_row']
                scisum[fully_masked] = 0.
                varsum[fully_masked] = 0.
                skysum[fully_masked] = 0.
            # NAN
            NANs = np.isnan(scisum)
            if np.any(NANs):
                msgs.warn("   NANs in the spectrum somehow...")
                boxmask[NANs] += mask_flags['NANs']
                scisum[NANs] = 0.
                varsum[NANs] = 0.
                skysum[NANs] = 0.
            # Check on specobjs
            if not specobjs[sl][o].check_trace(scitrace[sl]['traces'][:, o]):
                debugger.set_trace()
                msgs.error("Bad match to specobj in boxcar!")
            # Fill
            specobjs[sl][o].boxcar['wave'] = wvsum.copy()*units.AA  # Yes, units enter here
            specobjs[sl][o].boxcar['counts'] = scisum.copy()
            specobjs[sl][o].boxcar['var'] = varsum.copy()
            if np.sum(specobjs[sl][o].boxcar['var']) == 0.:
                debugger.set_trace()
            specobjs[sl][o].boxcar['sky'] = skysum.copy()  # per pixel
            specobjs[sl][o].boxcar['mask'] = boxmask.copy()
            # Find boxcar size
            slit_sz = []
            inslit = np.where(weight == 1.)
            for ii in range(weight.shape[0]):
                inrow = inslit[0] == ii
                if np.sum(inrow) > 0:
                    slit_sz.append(np.max(inslit[1][inrow])-np.min(inslit[1][inrow]))
            slit_pix = np.median(slit_sz)  # Pixels
            specobjs[sl][o].boxcar['size'] = slit_pix
    # Return
    return bgcorr

# This routine is deprecated
# TODO: (KBW) But it can still be called...
def obj_profiles(det, specobjs, sciframe, varframe, crmask,
                 scitrace, tilts, maskslits, slitpix,
                 extraction_profile='gaussian',
                 COUNT_LIM=25., doqa=True, pickle_file=None):
    """ Derive spatial profiles for each object
    Parameters
    ----------
    det : int
    specobjs : list
    sciframe : ndarray
      Sky subtracted science frame
    varframe : ndarray
    crmask : ndarray
    scitrace : list
    tilts : ndarray
    maskslits : ndarray

    Returns
    -------
    All internal on specobj and scitrace objects
    """
    # Init QA
    #
    sigframe = np.sqrt(varframe)
    slits = range(len(specobjs))
    gdslits = np.where(~maskslits)[0]
    # Loop on slits
    for sl in slits:
        if sl not in gdslits:
            continue
        # Loop on objects
        nobj = scitrace[sl]['nobj']
        if nobj == 0:
            continue
        scitrace[sl]['opt_profile'] = []
        msgs.work("Should probably loop on S/N")
        for o in range(nobj):
            msgs.info("Deriving spatial profile of object {0:d}/{1:d} in slit {2:d}/{3:d}".format(o+1, nobj, sl+1, len(specobjs)))
            # Get object pixels
            if scitrace[sl]['background'] is None:
                # The object for all slits is provided in the first extension
                objreg = np.copy(scitrace[0]['object'][:, :, o])
                wzro = np.where(slitpix != sl + 1)
                objreg[wzro] = 0.0
            else:
                objreg = scitrace[sl]['object'][:, :, o]
            # Calculate slit image
            slit_img = artrace.slit_image(scitrace[sl], o, tilts)
            # Object pixels
            weight = objreg.copy()
            # Identify good rows
            try:
                gdrow = np.where(specobjs[sl][o].boxcar['counts'] > COUNT_LIM)[0]
            except:
                debugger.set_trace()
            # Normalized image
            norm_img = sciframe / np.outer(specobjs[sl][o].boxcar['counts'], np.ones(sciframe.shape[1]))
            # Eliminate rows with CRs (wipes out boxcar)
            crspec = np.sum(crmask*weight, axis=1)
            cr_rows = np.where(crspec > 0)[0]
            weight[cr_rows, :] = 0.
            #
            if len(gdrow) > 100:  # Good S/N regime
                msgs.info("Good S/N for profile")
                # Eliminate low count regions
                badrow = np.where(specobjs[sl][o].boxcar['counts'] < COUNT_LIM)[0]
                weight[badrow, :] = 0.
                # Extract profile
                gdprof = (weight > 0) & (sigframe > 0.) & (~np.isnan(slit_img))  # slit_img=nan if the slit is partially on the chip
                slit_val = slit_img[gdprof]
                flux_val = norm_img[gdprof]
                #weight_val = sciframe[gdprof]/sigframe[gdprof]  # S/N
                weight_val = 1./sigframe[gdprof]  # 1/N
                msgs.work("Weight by S/N in boxcar extraction? [avoid CRs; smooth?]")
                # Fit
                fdict = dict(func=extraction_profile, deg=3, extrap=False)
                if fdict['func'] == 'gaussian':
                    fdict['deg'] = 2
                elif fdict['func'] == 'moffat':
                    fdict['deg'] = 3
                else:
                    msgs.error("Not ready for this type of object profile")
                msgs.work("Might give our own guess here instead of using default")
                guess = None
                # Check if there are enough pixels in the slit to perform fit
                if slit_val.size <= fdict['deg'] + 1:
                    msgs.warn("Not enough pixels to determine profile of object={0:s} in slit {1:d}".format(specobjs[sl][o].idx, sl+1) + msgs.newline() +
                              "Skipping Optimal")
                    fdict['extrap'] = True
                    scitrace[sl]['opt_profile'].append(copy.deepcopy(fdict))
                    continue
                # Fit the profile
                try:
                    mask, gfit = utils.robust_polyfit(slit_val, flux_val, fdict['deg'], function=fdict['func'], weights=weight_val, maxone=False, guesses=guess)
                except RuntimeError:
                    msgs.warn("Bad Profile fit for object={:s}." + msgs.newline() +
                              "Skipping Optimal".format(specobjs[sl][o].idx))
                    fdict['extrap'] = True
                    scitrace[sl]['opt_profile'].append(copy.deepcopy(fdict))
                    continue
                except ValueError:
                    debugger.set_trace()  # NaNs in the values?  Check
                msgs.work("Consider flagging/removing CRs here")
                # Record
                fdict['param'] = gfit.copy()
                fdict['mask'] = mask
                fdict['slit_val'] = slit_val
                fdict['flux_val'] = flux_val
                scitrace[sl]['opt_profile'].append(copy.deepcopy(fdict))
                specobjs[sl][o].optimal['fwhm'] = fdict['param'][1]  # Pixels
                if False: #msgs._debug['obj_profile']:
                    gdp = mask == 0
                    mn = np.min(slit_val[gdp])
                    mx = np.max(slit_val[gdp])
                    xval = np.linspace(mn, mx, 1000)
                    model = utils.func_val(gfit, xval, fdict['func'])
                    plt.clf()
                    ax = plt.gca()
                    ax.scatter(slit_val[gdp], flux_val[gdp], marker='.', s=0.7, edgecolor='none', facecolor='black')
                    ax.plot(xval, model, 'b')
                    # Gaussian too?
                    if False:
                        fdictg = dict(func='gaussian', deg=2)
                        maskg, gfitg = utils.robust_polyfit(slit_val, flux_val, fdict['deg'], function=fdictg['func'], weights=weight_val, maxone=False)
                        modelg = utils.func_val(gfitg, xval, fdictg['func'])
                        ax.plot(xval, modelg, 'r')
                    plt.show()
                    debugger.set_trace()
            elif len(gdrow) > 10:  #
                msgs.warn("Low extracted flux for obj={:s} in slit {:d}.  Not ready for Optimal".format(specobjs[sl][o].idx,sl+1))
                scitrace[sl]['opt_profile'].append({})
                continue
            elif len(gdrow) >= 0:  # limit is ">= 0" to avoid crash for gdrow=0
                msgs.warn("Low extracted flux for obj={:s} in slit {:d}.  Not ready for Optimal".format(specobjs[sl][o].idx, sl + 1))
                scitrace[sl]['opt_profile'].append({})
                continue
    # QA
    if doqa: #not msgs._debug['no_qa'] and doqa:
        msgs.info("Preparing QA for spatial object profiles")
#        qa.obj_profile_qa(slf, specobjs, scitrace, det)
        debugger.set_trace()  # Need to avoid slf
        obj_profile_qa(specobjs, scitrace, det)
    return


# This routine is deprecated, replaced by fit_profile_qa
def obj_profile_qa(slf, specobjs, scitrace, det):
    """ Generate a QA plot for the object spatial profile
    Parameters
    ----------
    """

    plt.rcdefaults()
    plt.rcParams['font.family']= 'times new roman'

    method = inspect.stack()[0][3]
    gdslits = np.where(~slf._maskslits[det-1])[0]
    for sl in range(len(specobjs)):
        if sl not in gdslits:
            continue
        # Setup
        nobj = scitrace[sl]['nobj']
        if nobj == 0:
            continue
        ncol = min(3, nobj)
        nrow = nobj // ncol + ((nobj % ncol) > 0)
        # Outfile
        outfile = qa.set_qa_filename(slf._basename, method, det=det, slit=specobjs[sl][0].slitid)
        # Plot
        plt.figure(figsize=(8, 5.0))
        plt.clf()
        gs = gridspec.GridSpec(nrow, ncol)

        # Plot
        for o in range(nobj):
            fdict = scitrace[sl]['opt_profile'][o]
            if 'param' not in fdict.keys():  # Not optimally extracted
                continue
            ax = plt.subplot(gs[o//ncol, o % ncol])

            # Data
            gdp = fdict['mask'] == 0
            ax.scatter(fdict['slit_val'][gdp], fdict['flux_val'][gdp], marker='.',
                       s=0.5, edgecolor='none')

            # Fit
            mn = np.min(fdict['slit_val'][gdp])
            mx = np.max(fdict['slit_val'][gdp])
            xval = np.linspace(mn, mx, 1000)
            fit = utils.func_val(fdict['param'], xval, fdict['func'])
            ax.plot(xval, fit, 'r')
            # Axes
            ax.set_xlim(mn,mx)
            # Label
            ax.text(0.02, 0.90, 'Obj={:s}'.format(specobjs[sl][o].idx),
                    transform=ax.transAxes, ha='left', size='small')

        plt.savefig(outfile, dpi=500)
        plt.close()

    plt.rcdefaults()

# This routine is deprecated, replaced by extract_optimal
# TODO: (KBW) But it can still be called...
def optimal_extract(specobjs, sciframe, varframe,
                    crmask, scitrace, tilts, mswave,
                    maskslits, slitpix, calib_wavelength='vacuum',
                    pickle_file=None, profiles=None):
    """ Preform optimal extraction
    Standard Horne approach

    Parameters
    ----------
    slf
    det
    specobjs
    sciframe
    varframe
    crmask
    scitrace
    COUNT_LIM
    pickle_file

    Returns
    -------
    newvar : ndarray
      Updated variance array that includes object model
    """
    # Inverse variance
    model_ivar = np.zeros_like(varframe)
    cr_mask = 1.0-crmask
    gdvar = (varframe > 0.) & (cr_mask == 1.)
    model_ivar[gdvar] = utils.calc_ivar(varframe[gdvar])
    # Object model image
    obj_model = np.zeros_like(varframe)
    gdslits = np.where(~maskslits)[0]
    # Loop on slits
    for sl in range(len(specobjs)):
        if sl not in gdslits:
            continue
        # Loop on objects
        nobj = scitrace[sl]['nobj']
        if nobj == 0:
            continue
        for o in range(nobj):
            msgs.info("Performing optimal extraction of object {0:d}/{1:d} in slit {2:d}/{3:d}".format(o+1, nobj, sl+1, len(specobjs)))
            # Get object pixels
            if scitrace[sl]['background'] is None:
                # The object for all slits is provided in the first extension
                objreg = np.copy(scitrace[0]['object'][:, :, o])
                wzro = np.where(slitpix != sl + 1)
                objreg[wzro] = 0.0
            else:
                objreg = scitrace[sl]['object'][:, :, o]
            # Fit dict
            fit_dict = scitrace[sl]['opt_profile'][o]
            if 'param' not in fit_dict.keys():
                continue
            # Slit image
            slit_img = artrace.slit_image(scitrace[sl], o, tilts)
            #msgs.warn("Turn off tilts")
            # Object pixels
            weight = objreg.copy()
            gdo = (weight > 0) & (model_ivar > 0)
            # Profile image
            prof_img = np.zeros_like(weight)
            prof_img[gdo] = utils.func_val(fit_dict['param'], slit_img[gdo],
                                             fit_dict['func'])
            # Normalize
            norm_prof = np.sum(prof_img, axis=1)
            prof_img /= np.outer(norm_prof + (norm_prof == 0.), np.ones(prof_img.shape[1]))
            # Mask (1=good)
            mask = np.zeros_like(prof_img)
            mask[gdo] = 1.
            mask *= cr_mask

            # Optimal flux
            opt_num = np.sum(mask * sciframe * model_ivar * prof_img, axis=1)
            opt_den = np.sum(mask * model_ivar * prof_img**2, axis=1)
            opt_flux = opt_num / (opt_den + (opt_den == 0.))
            # Optimal wave
            opt_num = np.sum(mswave * model_ivar * prof_img**2, axis=1)
            opt_den = np.sum(model_ivar * prof_img**2, axis=1)
            opt_wave = opt_num / (opt_den + (opt_den == 0.))
            # Replace fully masked rows with mean wavelength (they will have zero flux and ivar)
            full_mask = opt_num == 0.
            if np.any(full_mask):
                msgs.warn("Replacing fully masked regions with mean wavelengths")
                mnwv = np.mean(mswave, axis=1)
                opt_wave[full_mask] = mnwv[full_mask]
            if (np.sum(opt_wave < 1.) > 0) and calib_wavelength != "pixel":
                debugger.set_trace()
                msgs.error("Zero value in wavelength array. Uh-oh")
            # Optimal ivar
            opt_num = np.sum(mask * model_ivar * prof_img**2, axis=1)
            ivar_den = np.sum(mask * prof_img, axis=1)
            opt_ivar = opt_num * utils.calc_ivar(ivar_den)

            # Save
            specobjs[sl][o].optimal['wave'] = opt_wave.copy()*units.AA  # Yes, units enter here
            specobjs[sl][o].optimal['counts'] = opt_flux.copy()
            gdiv = (opt_ivar > 0.) & (ivar_den > 0.)
            opt_var = np.zeros_like(opt_ivar)
            opt_var[gdiv] = utils.calc_ivar(opt_ivar[gdiv])
            specobjs[sl][o].optimal['var'] = opt_var.copy()
            #specobjs[o].boxcar['sky'] = skysum  # per pixel

            # Update object model
            counts_image = np.outer(opt_flux, np.ones(prof_img.shape[1]))
            obj_model += prof_img * counts_image
            '''
            if 'OPTIMAL' in msgs._debug:
                debugger.set_trace()
                debugger.xplot(opt_wave, opt_flux, np.sqrt(opt_var))
            '''

    # KBW: Using variance_frame here produces a circular import.  I've
    # changed this function to return the object model, then this last
    # step is done in arproc.

#    # Generate new variance image
#    newvar = arproc.variance_frame(slf, det, sciframe, -1,
#                                   skyframe=skyframe, objframe=obj_model)
#    # Return
#    return newvar

    return obj_model


def boxcar_cen(slf, det, img):
    """ Simple boxcar down center of the slit

    Parameters
    ----------
    slf
    det
    img

    Returns
    -------
    spec : ndarray

    """
    # Extract a slit down the center (as in ararc, or should be!)
    ordcen = slf.GetFrame(slf._pixcen, det)
    op1 = ordcen+1
    op2 = ordcen+2
    om1 = ordcen-1
    om2 = ordcen-2
    # Extract
    censpec = (img[:,ordcen]+img[:,op1]+img[:,op2]+img[:,om1]+img[:,om2])/5.0
    if len(censpec.shape) == 3:
        censpec = censpec[:, 0].flatten()
    # Return
    return censpec


def func2d_fit_val(y, order, x=None, w=None):
    """
    Fit a polynomial to each column in y.

    if y is 2D, always fit along columns

    test if y is a MaskedArray
    """
    # Check input
    if y.ndim > 2:
        msgs.error('y cannot have more than 2 dimensions.')

    _y = np.atleast_2d(y)
    ny, npix = _y.shape

    # Set the x coordinates
    if x is None:
        _x = np.linspace(-1,1,npix)
    else:
        if x.ndim != 1:
            msgs.error('x must be a vector')
        if x.size != npix:
            msgs.error('Input x must match y vector or column length.')
        _x = x.copy()

    # Generate the Vandermonde matrix
    vand = np.polynomial.polynomial.polyvander(_x, order)

    # Fit with appropriate weighting
    if w is None:
        # Fit without weights
        c = np.linalg.lstsq(vand, _y.T)[0]
        ym = np.sum(c[:,:,None] * vand.T[:,None,:], axis=0)
    elif w.ndim == 1:
        # Fit with the same weight for each vector
        _vand = w[:,None] * vand
        __y = w[None,:] * _y
        c = np.linalg.lstsq(_vand, __y.T)[0]
        ym = np.sum(c[:,:,None] * vand.T[:,None,:], axis=0)
    else:
        # Fit with different weights for each vector
        if w.shape != y.shape:
            msgs.error('Input w must match y axis length or y shape.')
        # Prep the output model
        ym = np.empty(_y.shape, dtype=float)
        # Weight the data
        __y = w * _y
        for i in range(ny):
            # Weight the Vandermonde matrix for this y vector
            _vand = w[i,:,None] * vand
            c = np.linalg.lstsq(_vand, __y[i,:])[0]
            ym[i,:] = np.sum(c[:,None] * vand.T[:,:], axis=0)

    # Return the model with the appropriate shape
    return ym if y.ndim == 2 else ym[0,:]


