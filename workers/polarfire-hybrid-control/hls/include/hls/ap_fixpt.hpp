// Software-only shim for SmartHLS hls::ap_fixpt<W,I>
// For local testbench compilation only — NOT for synthesis.
// SmartHLS provides the real implementation on the build host.
#ifndef HLS_AP_FIXPT_HPP
#define HLS_AP_FIXPT_HPP

namespace hls {

template<int W, int I>
class ap_fixpt {
    double val;
public:
    ap_fixpt() : val(0) {}
    ap_fixpt(double v) : val(v) {}
    ap_fixpt(int v) : val(v) {}

    double to_double() const { return val; }

    ap_fixpt operator+(const ap_fixpt &o) const { return ap_fixpt(val + o.val); }
    ap_fixpt operator-(const ap_fixpt &o) const { return ap_fixpt(val - o.val); }
    ap_fixpt operator*(const ap_fixpt &o) const { return ap_fixpt(val * o.val); }

    template<int W2, int I2>
    ap_fixpt operator+(const ap_fixpt<W2,I2> &o) const { return ap_fixpt(val + o.to_double()); }
    template<int W2, int I2>
    ap_fixpt operator-(const ap_fixpt<W2,I2> &o) const { return ap_fixpt(val - o.to_double()); }
    template<int W2, int I2>
    ap_fixpt operator*(const ap_fixpt<W2,I2> &o) const { return ap_fixpt(val * o.to_double()); }

    bool operator>(const ap_fixpt &o) const { return val > o.val; }
    bool operator<(const ap_fixpt &o) const { return val < o.val; }
    bool operator>=(const ap_fixpt &o) const { return val >= o.val; }
    bool operator<=(const ap_fixpt &o) const { return val <= o.val; }

    ap_fixpt &operator=(double v) { val = v; return *this; }

    template<int W2, int I2>
    operator ap_fixpt<W2,I2>() const { return ap_fixpt<W2,I2>(val); }
};

} // namespace hls

#endif // HLS_AP_FIXPT_HPP
