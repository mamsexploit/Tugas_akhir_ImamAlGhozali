/*********************************************************************************************************************
 jquery.etc.js

 jQuery plugin for LCO's exposure time calculator.  Enabling this for an element will by default
 set up a click handler for that element that displays the ETC as a lightbox.  If the embed option
 is set, then instead of a lightbox, the ETC will be rendered immediately within the element.

 Lightbox usage:
    $('#some-element-id').etc();

 Embedded usage:
    $('#some-element-id').etc({embed:true});

 Example:

    <html>
        <head>
            <title>LCOGT Exposure Time Calculator Interface</title>
            <script src="https://ajax.googleapis.com/ajax/libs/jquery/1.10.2/jquery.min.js" ></script>
            <script src="https://ajax.googleapis.com/ajax/libs/jqueryui/1.10.2/jquery-ui.min.js"></script>
            <script type="text/javascript" src="https://lco.global/files/lco_etc/jquery.etc.js"></script>
            <script type="text/javascript">
                $(document).ready(function() {
                    $('#lightbox').etc();
                });
            </script>
        </head>
        <body>
            <a href="#" id="lightbox">LCOGT Exposure Time Calculator</a>
        </body>
    </html>

Order of Telescope/Instrument on website is:
  1m0 Sinistro, 
  2m0 Spectral,
  2m0 Muscat
  0m4 SBIG,
  0m4 QHY

 Authors: Andrew Pickles and Doug Thomas, LCOGT

 Daniel Harbeck 2023 simplifications to base flux estimates on actually measured photometric zeropoints.

********************************************************************************************************************/

var ETC = ETC || {};

ETC.debug = false;

ETC.log10f = function(x){
    return Math.log(x) / Math.LN10;
};

ETC.log = function(){
    if (ETC.debug && typeof console !== "undefined" && typeof console.log=="function")
        console.log(arguments);
};

ETC.radial_integrate_gauss = function (R,sigma) {

   result = (1 - Math.pow (Math.E, -1. * (R*R)/2/sigma/sigma)) ;/// (2* Math.PI * sigma * sigma);
   ETC.log ("Integrate gauss ", R, sigma, "->", result)
   return result;
};


ETC.calculate_sme = function(input){
    ETC.log(input);

    // SEVEN INPUT PARAMETERS (ires depends on itel)
    var S_N = parseFloat(input.S_N);
    var mag = parseFloat(input.mag);
    var etime = input.etime !== "" ? parseFloat(input.etime) : 0;
    var itel = parseInt(input.itel);
    var ires = itel == 8 ? 1 : 0;  // if itel is 8 (2m0 FLOYDS), set ires to 1
    var filter = input.filter;
    var moonp = parseInt(input.moonp); // new = 0; half = 1; full = 2
    var air= parseFloat(input.air); // airmass

    var adiam  = 3.0;   // Aperture diameter in arcsec
    var ifilt = 2;      // Index for filter array; default (2) is 'V' filter
    var Nlambda;        // Nphotons/A/cm^2/sec
    var Nobj;           // Nphotons/sec from object
    var g_e;
    var MAGinst;        // Calculated instrumental mag (eg. in Sextractor)
    var DNinst;         // Calculated instrumental Flux in DN
    var Npix;           // Number of pixels in aperture
    var Nas;            // Number of square arcsec in aperture
    var Nbkgd;          // Number of photons/sec in background
    var NbDN;           // Number of DN in background in etime
    var throughput;     // total QE
    var endloop = 0;
    var S_Nt = S_N;     // S/N achieved in exp time
    var S_Nlim = S_N;
    var magt = mag;     // Mag achieved in exp time
    var t = etime;      // exposure time in sec
    var NeObj;
    var NeBkgd;
    var NeDark;         // Nelect due to dark current
    var NeRon;          // Nelect due to readout
    var PkDN;           // estimate of peak DN in aperture (1/3 of stated aperture)
    var result;         // Options are: s => calculate S/N, m => calc mag, e => calc exposure time
    var resoln = 5;
    var dark = 0.0;     // dark current (e- per pixel per second) 
    var ron = 0.0;      // readout noise (e- per pix)
    var gain = 0.0;     // gain (e- per DN)

    var spfrac = 0.4;   // ADDITIONAL transmission through spectrometers
    var saturated = itel == 1 ? 100000.0 : 40000.0;        // Saturation counts. Only Sinistro (itel=1) has higher limit.
    ETC.log ('exposure time', etime)
    // Names of filters
    var Filt= ['U', 'B', 'V', 'R', 'I', 'u', 'g', 'r', 'i', 'Z', 'Y'];

    // Collecting areas per ITEL: 0m4, 1m0, 0m35, 2m0, 2m0  in cm^2; not used in code.
    var Carea = [1200.0, 6260.0, 660, 27000.0, 27000.0];

    // Pixel scale per ITEL: 0m4 SBIG, 1m0 Sinistro, 0m35QHY, 2m0 Spectral, 2m0 MuSCAT3
   // in ubits of arcsec / pixel
    var ApixelTable = [0.57, 0.389, 0.73,  0.304, 0.27]; // from website
    var apixel = ApixelTable[itel]; // retrieve pixel scale for selected telescope/instrument

    // Gain in units of e- / ADU
    var gainTable = [1.6, 2.3, 0.7, 7.7,  1.9]
    gain = gainTable[itel]

    // Readnoise in units of e-
    var readnoiseTable = [14, 8, 3, 11, 14.5]
    ron = readnoiseTable[itel]

    // dark current input, units of e-/pix/sec
    var darkCurrentTable = [0.02, 0.002, 0.04, 0.002, 0.005]
    dark = darkCurrentTable[itel]

    // saturation limit in electrons per unbinned pixel
    var saturationLimitTable = [65000*1.6, 10000,47000, 71000, 462000]
    saturationLimit = saturationLimitTable[itel]

    // Filter central wavelengths in microns
    var Fcent = [0.350, 0.437, 0.549, 0.653, 0.789, 0.354, 0.476, 0.623, 0.760, 0.853, 0.975]; // 20200921

    // Filter nominal (effective) bandwidths in microns
    var Fband = [0.050, 0.107, 0.083, 0.137, 0.128, 0.057, 0.140, 0.135, 0.148, 0.113, 0.118]; // 20200921

    // Standard flux (in Jy) for 0 mag (Vega = UBVRI or AB = ugriz) for each filter
    //var Fjy = [1755, 4050, 3690, 3060, 2540, 3680, 3631, 3631, 3631, 3631, 3631]; // original

    // Hayes & Latham extinction coeffs for 2200m (mag per airmass)
    var Ext= [0.54, 0.23, 0.12, 0.09, 0.04, 0.59, 0.14, 0.08, 0.06, 0.04, 0.03]; // 20200921

    // Zero point magnitudes for each telescope/filter  - ADJUST ZERO-POINTS here

    // Must be in units of log(e-/sec), i.e, based on images corrected for gain.
    //  ugriz reviewd DRH Feb 1 2023 ; Y data not updated yet
    // Johnson reviewd DRH Feb 2 2023
    // Entires 0.00 inidcate no daota or no filter installed (e.g., Muscat)
    //  ugriz reviewd DRH Feb 1 2023
    // Sinistro all filters DRH Feb 6 2023
    var photZeropointTable = [
    // ['U', 'B',   'V',   'R',   'I',   'u',   'g',   'r',  'i',   'Z',  'Y'];
 	[18.0, 20.3,  20.7,  21.2,  20.3,  16.11, 21.4,  21.5,  20.75, 19.4,  17.8], //0m4K  (SBIG)
	[21.4, 23.5,  23.5,  23.8,  23.2,  22.45, 24.3,  23.8,  23.5,  22.2,  20.3], //1mF (Sinistro)
	[ 0.0, 21.4,  21.4,  21.2,  20.3,  17.5,  21.8,  21.2,  20.1,  18.4,   0.0], //0m4K  (QHY CHECK ME!!!)
	[21.3, 24.4,  24.6,  24.9,  24.1,  21.4,  25.4,  25.25, 24.75, 23.75, 21.6], //2mF (Spectral)
	[ 0.0,  0.0,   0.0,   0.0,   0.0,   0.0,  25.4,  25.2,  24.5,  24.3,  0.0 ], //2mE (MuSCAT3)
   ];

    // Sky brightness in mags/sq-as (Vega or AB) for each filter at new, half, full moon
    var Msky = [
     // ['U',    'B', 'V', 'R',  'I',   'u', 'g',  'r',  'i',   'Z',  'Y'];
        [23.0, 22.5, 21.6, 20.6, 19.8, 23.5, 22.0, 21.1, 20.6, 20.2, 19.4], // new moon
        [20.0, 20.5, 20.3, 20.0, 18.8, 21.0, 20.3, 20.2, 19.7, 19.2, 18.0], // half
        [17.0, 17.8, 17.5, 17.4, 17.0, 18.0, 17.6, 17.5, 17.5, 16.8, 16.5]  // full
    ];

    if ((S_Nt > 0.0) && (mag > 0.0)) { // if values for S/N and Mag are entered, then find Exp Time.
        t = 1.0;  // set initial value for exp time
        result = 'e';  
    } else if ((S_Nt > 0.0) && (etime > 0.0)) { // if values for S/N and Exp Time are entered, then find Mag.
        magt = 30.0; // set initial value for magnitude
        result = 'm';
    } else { // Last option: Find S/N
        result = 's';
    }

    ifilt = Filt.indexOf(filter); // assign the Filt-array index of the selected filter to "ifilt"
    var extco = Ext[ifilt]; // assign value of extinction coeff appropriate for selected filter to "extco"

    // Calculations start here
    var airmass_correction = (air - 1.0) * extco; // acorr is [(Mag at air)-(Mag at zenith)]; recall: air x extco = mag

    zeropoint = photZeropointTable[itel][ifilt] // photometric zeropoint in e-; derive from photzp app.
    Nas  = Math.PI / 4 * adiam*adiam; // Number of sq.arcsec in aperture, simply PI*[D/2]^2.
    Npix = Nas/apixel/apixel;  // Number of pix in aperture; no quantisation done
    skymag = Msky[moonp][ifilt];

    while (endloop < 1) {
      // fluxes
      var mag_at_airmass = magt + airmass_correction; // selected mag modified for airmass
      Nobj  = Math.pow(10.0, -0.4* (mag_at_airmass - zeropoint));  // e-/second from object.
      Nbkgd = Math.pow(10.0, -0.4* (skymag - zeropoint)); // e-/sec/arcsec^2 from sky. DRH: Check This!!!!
      NbDN  = Nbkgd*apixel*apixel // e-/sec/pixel from sky background
      Nbkgd = Nbkgd*Nas; // e-/sec in aperture

      NeDark= Npix*dark; // Nelect/sec due to dark current
      NeRon = Npix*ron*ron; // Nelect due to readout ([e-*pix]^2)

      // counts over the exposure time
      NeObj  = Nobj*t; // Nelect from source over exp time
      NeBkgd = Nbkgd*t; // Nelect from bkgd in aperture over exp time
      NbDN   = NbDN*t; // e-/pix from sky skgd
      NeDark = NeDark*t; // Nelect from dark current

      // Check what the peak pixel would  could be (which is object flux + background)
      var seeing = 2  // fwhm in pixels Assume 2'' seeing; make this a parameter?
      var gauss_sigma = seeing / 2.354; // FWHM -> sigma in gaussian distribution, in arcseconds

      // approximate the pixel as round; easier to calculate.
      PkDN = NeObj * ETC.radial_integrate_gauss(apixel/2 , gauss_sigma);
      PkDN = PkDN + NbDN

      S_Nt = NeObj / Math.sqrt( NeObj + NeBkgd + NeDark + NeRon ); // Here's the actual S/N equation for t seconds.

      if( result=='e') { // If exp time requested, and
        if(S_Nt < S_Nlim) { // If calculated S/N hasn't exceeded input S/N,
          t += 1; // Then add 1 second, for all cameras
        } else endloop=1; // If input S/N reached, then quit.

      } else if( result=='m') { // If mag limit requested, and
        if (S_Nt < S_Nlim) magt -= 0.1; // If calculated S/N hasn't exceeded input S/N, then brighten by 0.1 mag
        else endloop=1; // If input S/N reached, then quit.

      } else endloop=1; // If S/N requested, then quit.
    }

    // Rounding
    S_Nt = Math.round(10.0*S_Nt); S_Nt = S_Nt/10.0;
    mag = mag_at_airmass-airmass_correction;
    mag = Math.round(10.0*mag); mag = mag/10.0;
    NeObj = Math.round(10.0*NeObj); NeObj = NeObj/10.0;
    NeBkgd = Math.round(10.0*NeBkgd); NeBkgd = NeBkgd/10.0;
    NeDark = Math.round(10.0*NeDark); NeDark = NeDark/10.0;
    NeRon = Math.round(10.0*NeRon); NeRon = NeRon/10.0;
    NbDN = Math.round(10.0*NbDN); NbDN = NbDN/10.0;
    PkDN = Math.round(10.0*PkDN); PkDN = PkDN/10.0;
    Npix = Math.round(10.0*Npix); Npix = Npix/10.0;
    Nas = Math.round(10.0*Nas); Nas = Nas/10.0;

    var Saturated=saturationLimit

    var r= { // These are the values sent to the screen as output?
        S_Nt: S_Nt,
        mag: mag,
        t: t,
        dqe: throughput,
        apixel: apixel,
        Nas: Nas,
        Msky: skymag,
        NbDN: NbDN,
        PkDN: PkDN,
        extco: extco,
        NeObj: NeObj,
        NeBkgd: NeBkgd,
        NeDark: NeDark,
        NeRon: NeRon,
        Npix: Npix,
        dark: dark,
        ron: ron,
        gain: gain,
        adiam: adiam,
        carea:  Carea[itel],
        fcent: Fcent[ifilt],
        saturated: saturated
    };
    ETC.log(r);
    return r;
};

//
// jquery plugin
//
(function (factory) {
	if (typeof define === 'function' && define.amd) {
		// AMD. Register as an anonymous module.
		define(['jquery'], factory);
	} else {
		// Browser globals
		factory(jQuery);
	}
}(function ($) {
    if (!Array.prototype.indexOf) {
        Array.prototype.indexOf = function(obj, start) {
             for (var i = (start || 0), j = this.length; i < j; i++) {
                 if (this[i] === obj) { return i; }
             }
             return -1;
        }
    }

    var _defaults = {
        url: 'etc.html#lcogt-etc',
        embed: false
    };

	var methods =
	{
		init: function(options)
		{
			return this.each(function()
			{
				var self = $(this);
				var settings = $.extend({}, _defaults);

				if (options)
					settings = $.extend(settings, options);

                var $link = $(self);
                var $dialog = $('<div></div>');
                $dialog.load(settings.url, function(){
                    if(options && options.embed){
                        self.css('width','720px');
                        self.append($dialog);
                        $('#lcogt-etc').show();
                    }
                    else{
                        $dialog.dialog({
                            autoOpen: false,
                            modal:true,
                            title: 'LCOGT Exposure Time Calculator',
                            minWidth: 700,
                            show:1000,
                            resizable: false,
                            buttons: [],
                            closeOnEscape: true
                        });
                    }

                    var $inputs = $('#lcogt-etc :input');
                    $inputs.on('keydown', function(e){
                        $('#lcogt-etc :input').tooltip("close");
                    });
                    $inputs.on('focus', function(e){
                        $(this).tooltip("open");
                    });
                    var position = { my:'left center',  at:'right+10 center' };
                    position.collision = 'none';
                    $inputs.tooltip();
                    $('input[value="right"]').trigger('change');
                    $inputs.tooltip('option', 'position', position);
                    $inputs.tooltip('option', 'tooltipClass', 'right');

                    $('#lcogt-etc-inputForm').on('submit', function(e){
                        e.preventDefault();
                        var values = {};
                        $.each($('#lcogt-etc-inputForm').serializeArray(), function(i, field) {
                            values[field.name] = field.value;
                        });
                        var output = ETC.calculate_sme(values);
                        //ETC.log(output);
                        $f=$('#lcogt-etc-outputForm');
                        $.each(output, function(name, value){
                            var sel='input[name=' + name + ']';
                            $f.find(sel).val(value);
                        });
                        if(output.PkDN > output.saturated){
                            $f.find('input[name=PkDN]').css('color', '#F00');
                            $f.find('.saturation').html("<br/>Saturation may occur.  Consider reducing the exposure or defocusing the telescope.").css('color','#F00');
                        }
                        else {
                            $f.find('input[name=PkDN]').css('color', '#000');
                            $f.find('.saturation').html("").css('color','#000');
                        }
                        return true;
                    });

                    $('#lcogt-etc-advanced').hide();
                    $("#lcogt-etc-show-advanced").click(function(){
                        $('#lcogt-etc-advanced').toggle("slow", function(){
                            if ($('#lcogt-etc-advanced').is(':visible'))
                                $('#lcogt-etc-show-advanced').html('(Additional values &#9652;)');
                            else
                                $('#lcogt-etc-show-advanced').html('(Additional values &#9662;)');
                        });
                    });
                });

                if (!(options && options.embed)){
                    $link.on('click', function() {
                        $('#lcogt-etc').show();
                        $dialog.dialog('open');
                        return false;
                    });
                }
            });
        }
    };

	// etc entry
	$.fn.etc = function(method)
	{
		if(methods[method]) { return methods[method].apply(this, Array.prototype.slice.call(arguments, 1)); }
		else if(typeof method === "object" || !method) { return methods.init.apply(this, arguments); }
		else { $.error("Method "+ method + " does not exist on jQuery.etc.js"); }
	};

}));
