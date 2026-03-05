from scipy.signal import correlate
import numpy as np
from pathlib import Path
from .logging_config import setup_logging
import logging
from scipy.interpolate import interp1d
import os

class SignalAnalysis():
    """
    Class for analyzing signals, particularly for finding shifts and correlations between a sweep signal and a reference signal.
    """

    def __init__(self, config):
        # Setup Logging
        self.cfg = config
        log_path = self.cfg.get('paths', {}).get('logs', './logs')
        log_file = os.path.join(log_path, 'signal_analysis.log')
        self.logger = logging.getLogger('SignalAnalysis')
        setup_logging(self.logger, log_file)

        self.logger.info("SignalAnalysis initialized.")
    
    @staticmethod
    def downsample_signals(sweep_signal,reference_signal):
        """
        It makes sure that both signals have the same sampling rate by downsampling the one with the higher sampling rate.
        """

        sweep_signal_x = sweep_signal['x']
        sweep_signal_y = sweep_signal['y']
        reference_signal_x = reference_signal['x']
        reference_signal_y = reference_signal['y']
        dx_sweep = sweep_signal_x[1] - sweep_signal_x[0]
        dx_reference = reference_signal_x[1] - reference_signal_x[0]

        if dx_reference < dx_sweep:
            reference_signal_x_new = np.arange(reference_signal_x[0], reference_signal_x[-1], dx_sweep)
            reference_signal_y_new = interp1d(reference_signal_x, reference_signal_y, kind='linear', fill_value='extrapolate')(reference_signal_x_new)
            reference_signal = {'x': reference_signal_x_new, 'y': reference_signal_y_new}
            return sweep_signal, reference_signal
        elif dx_sweep < dx_reference:
            sweep_signal_x_new = np.arange(sweep_signal_x[0], sweep_signal_x[-1], dx_reference)
            sweep_signal_y_new = interp1d(sweep_signal_x, sweep_signal_y, kind='linear', fill_value='extrapolate')(sweep_signal_x_new)
            sweep_signal = {'x': sweep_signal_x_new, 'y': sweep_signal_y_new}
            return sweep_signal, reference_signal
        else:
            # If both signals have the same sampling rate, return them unchanged
            return sweep_signal, reference_signal
    

    @staticmethod
    def find_shift(sweep_signal, reference_signal):
        """
        Find how much the reference signal is shifted inside the sweep signal.
        """

        # sometimes there are artifacts at the beginning and end of the sweep signal
        sweep_signal_cropped = {}
        sweep_signal_cropped['x'] = sweep_signal['x'][10:-10]
        sweep_signal_cropped['y'] = sweep_signal['y'][10:-10]
        crop_length = sweep_signal['x'][10] - sweep_signal['x'][0]
        downsampled_sweep_signal, downsampled_reference_signal = SignalAnalysis.downsample_signals(sweep_signal_cropped, reference_signal)
        dx = downsampled_sweep_signal['x'][1] - downsampled_sweep_signal['x'][0]

        # calculate the cross-correlation between the cropped sweep signal and reference signal
        correlation = correlate(downsampled_sweep_signal['y'], downsampled_reference_signal['y'], mode='full')

        # find the index of the maximum correlation value
        # and adjust it to account for the cropping (+10)
        max_ind = (np.argmax(correlation) - (len(downsampled_reference_signal['y']) - 1))
        shift = downsampled_sweep_signal['x'][max_ind] - downsampled_reference_signal['x'][0]
        return shift
    
    @staticmethod
    def find_window(sweep_signal, reference_signal, shift):
        """
        Returns the window in which both signals overlap after applying the shift.
        """
        downsampled_sweep_signal, downsampled_reference_signal = SignalAnalysis.downsample_signals(sweep_signal, reference_signal)
        ref_shifted_min = downsampled_reference_signal['x'][0] + shift
        ref_shifted_max = downsampled_reference_signal['x'][-1] + shift
        sweep_min = downsampled_sweep_signal['x'][0]
        sweep_max = downsampled_sweep_signal['x'][-1]
        x_window_min = np.max(np.array([sweep_min, ref_shifted_min]))
        x_window_max = np.min(np.array([sweep_max, ref_shifted_max]))
        ind_sweep_start = np.where(downsampled_sweep_signal['x'] >= x_window_min)[0][0]
        ind_sweep_end = np.where(downsampled_sweep_signal['x'] <= x_window_max)[0][-1]
        ind_ref_start = np.where((downsampled_reference_signal['x'] + shift) >= x_window_min)[0][0]
        ind_ref_end = ind_ref_start + (ind_sweep_end - ind_sweep_start)
        if x_window_min >= x_window_max:
            return {}, {}
        sweep_signal_window = {}
        sweep_signal_window['x'] = downsampled_sweep_signal['x'][ind_sweep_start:ind_sweep_end]
        sweep_signal_window['y'] = downsampled_sweep_signal['y'][ind_sweep_start:ind_sweep_end]
        reference_signal_window = {}
        reference_signal_window['x'] = downsampled_reference_signal['x'][ind_ref_start:ind_ref_end]
        reference_signal_window['y'] = downsampled_reference_signal['y'][ind_ref_start:ind_ref_end]
        if len(sweep_signal_window['x']) == 0 or len(reference_signal_window['x']) == 0:
            return {}, {}
        return sweep_signal_window, reference_signal_window

    @staticmethod
    def match_signals(sweep_signal, reference_signal):
        """
        Matches the amplitude and offset of the reference signal to the sweep signal using least squares optimization.
        """
        sweep_signal_zeroavg = sweep_signal - np.mean(sweep_signal)
        reference_signal_zeroavg = reference_signal - np.mean(reference_signal)
        a_opt = np.sum(reference_signal_zeroavg * sweep_signal_zeroavg) / np.sum(reference_signal_zeroavg**2)
        b_opt = np.mean(sweep_signal) - a_opt * np.mean(reference_signal)
        matched_reference_signal = a_opt * reference_signal + b_opt
        matched_sweep_signal = sweep_signal
        return matched_sweep_signal, matched_reference_signal, b_opt, a_opt

    @staticmethod
    def find_correlation(sweep_signal,reference_signal):
        """
        Finds the correlation coefficient between the sweep signal and reference signal after aligning and matching them.
        """
        downsampled_sweep_signal, downsampled_reference_signal = SignalAnalysis.downsample_signals(sweep_signal, reference_signal)
        sweep_signal = downsampled_sweep_signal
        reference_signal = downsampled_reference_signal
        dx = downsampled_sweep_signal['x'][1] - downsampled_sweep_signal['x'][0]

        shift = SignalAnalysis.find_shift(sweep_signal,reference_signal)
        len_sweep_signal = downsampled_sweep_signal['x'][-1] - downsampled_sweep_signal['x'][0]

        if shift > len_sweep_signal or shift < -len_sweep_signal:
            return 0, 0
        
        sweep_signal_window, reference_signal_window = SignalAnalysis.find_window(sweep_signal, reference_signal, shift)
        if (len(sweep_signal_window['y']) == 0) or (len(reference_signal_window['y'])==0):
            return 0,0
        len_window = (sweep_signal_window['x'][-1] - sweep_signal_window['x'][0])/(reference_signal['x'][-1] - reference_signal['x'][0])
        matched_sweep_signal, matched_reference_signal, matched_offset, matched_amplitude = SignalAnalysis.match_signals(sweep_signal_window['y'], reference_signal_window['y'])
        matched_reference_signal_zeroavg = matched_reference_signal - np.mean(matched_reference_signal)
        matched_sweep_signal_zeroavg = matched_sweep_signal - np.mean(matched_sweep_signal)
        r_coeff = np.sum(matched_reference_signal_zeroavg * matched_sweep_signal_zeroavg) / np.sqrt(np.sum(matched_reference_signal_zeroavg**2) * np.sum(matched_sweep_signal_zeroavg**2))

        return r_coeff, len_window, matched_offset, matched_amplitude