/* Tied 12-parameter extension of Gpufit QSL lorentz8_linear.cuh.
 * Upstream commit 960a4df49bcbed115778f07407350a18ade14c9b, MIT.
 * Preserve LICENSE.Gpufit.txt. Prepared only; no compiled result exists.
 * p=[offset,slope,FWHM,shared amplitude,center0,...,center7].
 * x is centered MHz; slope multiplies x/65, matching the frozen experiment.
 */
__device__ void calculate_lorentz8_tied_linear(
    REAL const *p, int const n_fits, int const n_points,
    REAL *value, REAL *derivative, int const point_index,
    int const fit_index, int const chunk_index,
    char *user_info, std::size_t const user_info_size)
{
    REAL x = reinterpret_cast<REAL *>(user_info)[point_index];
    REAL *j = derivative + point_index;
    REAL g = p[2]/2;
    value[point_index] = p[0] + p[1]*x/65;
    j[0*n_points] = 1;
    j[1*n_points] = x/65;
    j[2*n_points] = 0;
    j[3*n_points] = 0;
    for (int k=0; k<8; ++k) {
        REAL d = x-p[4+k];
        REAL den = d*d+g*g;
        REAL l = g*g/den;
        value[point_index] += p[3]*l;
        j[2*n_points] += p[3]*g*d*d/(den*den);
        j[3*n_points] += l;
        j[(4+k)*n_points] = 2*p[3]*g*g*d/(den*den);
    }
}
