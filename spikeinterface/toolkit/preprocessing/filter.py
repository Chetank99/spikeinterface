import scipy.signal

from .basepreprocessor import BasePreprocessor, BasePreprocessorSegment

from .tools import get_chunk_with_margin


_common_filter_docs = \
    """**filter_kwargs: keyword arguments for parallel processing:
            * filter_order: order
                The order of the filter
            * filter_mode: 'sos or 'ba'
                'sos' is bi quadratic and more stable than ab so thery are prefered.
            * ftype: str
                Filter type for iirdesign ('butter' / 'cheby1' / ... all possible of scipy.signal.iirdesign)
    """


class FilterRecording(BasePreprocessor):
    """
    Generic filter class based on:
      * scipy.signal.iirfilter
      * scipy.signal.filtfilt or scipy.signal.sosfilt
    BandpassFilterRecording is built on top of it.

    Parameters
    ----------
    recording: Recording
        The recording extractor to be re-referenced
    band: float or list
        If float, cutoff frequency in Hz for 'lowpass' and 'highpass' filter types
        If list. band (low, high) in Hz for 'bandpass' and 'bandstop' filter types
    btype: str
        Type of the filter ('bandpass', 'lowpass', 'highpass', 'bandstop')
    margin_ms: float
        Margin in ms on border to avoid border effect
    dtype: dtype or None
        The dtype of the returned traces. If None, the dtype of the parent recording is used
    {}
    Returns
    -------
    filter_recording: FilterRecording
        The filtered recording extractor object

    """
    name = 'filter'

    def __init__(self, recording, band=[300., 6000.], btype='bandpass',
                 filter_order=5, ftype='butter', filter_mode='sos', margin_ms=5.0,
                 dtype=None):

        assert btype in ('bandpass', 'lowpass', 'highpass', 'bandstop')
        assert filter_mode in ('sos', 'ba')

        # coefficient
        sf = recording.get_sampling_frequency()
        if btype in ('bandpass', 'bandstop'):
            assert len(band) == 2
            Wn = [e / sf * 2 for e in band]
        else:
            Wn = float(band) / sf * 2
        N = filter_order
        # self.coeff is 'sos' or 'ab' style
        coeff = scipy.signal.iirfilter(N, Wn, analog=False, btype=btype, ftype=ftype, output=filter_mode)

        BasePreprocessor.__init__(self, recording, dtype=dtype)
        dtype_base = self.get_dtype()
        self.annotate(is_filtered=True)

        margin = int(margin_ms * sf / 1000.)
        for parent_segment in recording._recording_segments:
            self.add_recording_segment(FilterRecordingSegment(parent_segment, coeff, filter_mode, margin,
                                                              dtype_base))

        self._kwargs = dict(recording=recording.to_dict(), band=band, btype=btype,
                            filter_order=filter_order, ftype=ftype, filter_mode=filter_mode, margin_ms=margin_ms)


class FilterRecordingSegment(BasePreprocessorSegment):
    def __init__(self, parent_recording_segment, coeff, filter_mode, margin, dtype):
        BasePreprocessorSegment.__init__(self, parent_recording_segment)

        self.coeff = coeff
        self.filter_mode = filter_mode
        self.margin = margin
        self.dtype = dtype

    def get_traces(self, start_frame, end_frame, channel_indices):
        traces_chunk, left_margin, right_margin = get_chunk_with_margin(self.parent_recording_segment,
                                                                        start_frame, end_frame, channel_indices,
                                                                        self.margin)

        if self.filter_mode == 'sos':
            filtered_traces = scipy.signal.sosfiltfilt(self.coeff, traces_chunk, axis=0)
        elif self.filter_mode == 'ba':
            b, a = self.coeff
            filtered_traces = scipy.signal.filtfilt(b, a, traces_chunk, axis=0)

        if right_margin > 0:
            filtered_traces = filtered_traces[left_margin:-right_margin, :]
        else:
            filtered_traces = filtered_traces[left_margin:, :]
        return filtered_traces.astype(self.dtype)


class BandpassFilterRecording(FilterRecording):
    """
    Bandpass filter of a recording

    Parameters
    ----------
    recording: Recording
        The recording extractor to be re-referenced
    freq_min: float
        The highpass cutoff frequency in Hz
    freq_max: float
        The lowpass cutoff frequency in Hz
    margin_ms: float
        Margin in ms on border to avoid border effect
    dtype: dtype or None
        The dtype of the returned traces. If None, the dtype of the parent recording is used
    {}
    Returns
    -------
    filter_recording: BandpassFilterRecording
        The bandpass-filtered recording extractor object
    """
    name = 'bandpass_filter'

    def __init__(self, recording, freq_min=300., freq_max=6000., margin_ms=5.0, dtype=None, **filter_kwargs):
        FilterRecording.__init__(self, recording, band=[freq_min, freq_max], margin_ms=margin_ms, dtype=dtype,
                                 **filter_kwargs)
        self._kwargs = dict(recording=recording.to_dict(), freq_min=freq_min, freq_max=freq_max, margin_ms=margin_ms)
        self._kwargs.update(filter_kwargs)


class NotchFilterRecording(BasePreprocessor):
    """
    Parameters
    ----------
    recording: RecordingExtractor
        The recording extractor to be notch-filtered
    freq: int or float
        The target frequency in Hz of the notch filter
    q: int
        The quality factor of the notch filter
    {}
    Returns
    -------
    filter_recording: NotchFilterRecording
        The notch-filtered recording extractor object
    """
    name = 'notch_filter'

    def __init__(self, recording, freq=3000, q=30, margin_ms=5.0, dtype=None):
        # coeef is 'ba' type
        fn = 0.5 * float(recording.get_sampling_frequency())
        coeff = scipy.signal.iirnotch(freq / fn, q)

        BasePreprocessor.__init__(self, recording, dtype=dtype)
        dtype_base = self.get_dtype()
        self.annotate(is_filtered=True)

        sf = recording.get_sampling_frequency()
        margin = int(margin_ms * sf / 1000.)
        for parent_segment in recording._recording_segments:
            self.add_recording_segment(FilterRecordingSegment(parent_segment, coeff, 'ba', margin, dtype_base))

        self._kwargs = dict(recording=recording.to_dict(), freq=freq, q=q, margin_ms=margin_ms)


# functions for API

def filter(recording, engine='scipy', **kwargs):
    if engine == 'scipy':
        return FilterRecording(recording, **kwargs)
    elif engine == 'opencl':
        from .filter_opencl import FilterOpenCLRecording
        return FilterOpenCLRecording(recording, **kwargs)


filter.__doc__ = FilterRecording.__doc__.format(_common_filter_docs)


def bandpass_filter(*args, **kwargs):
    return BandpassFilterRecording(*args, **kwargs)


bandpass_filter.__doc__ = BandpassFilterRecording.__doc__.format(_common_filter_docs)


def notch_filter(*args, **kwargs):
    return NotchFilterRecording(*args, **kwargs)


notch_filter.__doc__ = NotchFilterRecording.__doc__.format(_common_filter_docs)
