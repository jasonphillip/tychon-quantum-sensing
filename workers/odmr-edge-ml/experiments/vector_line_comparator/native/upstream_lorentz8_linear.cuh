/* Description of the calculate_lorentz_8p function
* ==============================================
*
* This function calculates the values of 8 one-dimensional lorentzian model 
* functions and their partial derivatives with respect to the model parameters. 
* Also included is a linear baseline (y = mx + c)
*
* This function makes use of the user information data to pass in the 
* independent variables (X values) corresponding to the data.  The X values
* must be of type REAL.
*
* How the X values are handled:
*
*       The user_info array contains the X values for 'one' fit, which are
*       used for all fits. The size of the user_info array (in bytes) must
*       equal sizeof(REAL) * n_points.
*
* Parameters:
*
* parameters: An input vector of model parameters.
*             first the background:
*             p[0]: baseline/bground offset (c)
*             p[1]: baseline/bground gradient (m)
*             then for each peak 'n'(e.g. 0-7 for 8 peaks):
*             p[n+2+0]: FWHM of peak n 
*             p[n+2+1]: position (frequency) of peak n
*             p[n+2+2]: amplitude of peak n 
*
* n_fits: The number of fits. (not used)
*
* n_points: The number of data points per fit.
*
* value: An output vector of model function values.
*
* derivative: An output vector of model function partial derivatives.
*
* point_index: The data point index.
*
* fit_index: The fit index. (not used)
*
* chunk_index: The chunk index. (not used)
*
* user_info: An input vector containing user information. 
*
* user_info_size: The size of user_info in bytes. 
*
* Calling the calculate_lorentz8 function
* ======================================
*
* This __device__ function can be only called from a __global__ function or an other
* __device__ function.
*
*/
__device__ void calculate_lorentz8_linear(
    float const * parameters,
    int const n_fits,
    int const n_points,
    float * value,
    float * derivative,
    int const point_index,
    int const fit_index,
    int const chunk_index,
    char * user_info,
    std::size_t const user_info_size)
{
    // indices (track independent sweep vector values, 'x' (i.e. taus or freqs))

    REAL * user_info_float = (REAL*)user_info;
    REAL x = user_info_float[point_index];

    // parameters

    REAL const * p = parameters;
    /*
    *             first the background:
    *             p[0]: baseline/bground offset (c)
    *             p[1]: baseline/bground gradient (m)
    *
    *             then for each peak 'n':
    *             p[n+2+0]: FWHM of peak n 
    *             p[n+2+1]: position (frequency) of peak n
    *             p[n+2+2]: amplitude of peak n 
    */
    
    // REAL const baseline = p[1] * x + p[0];

    value[point_index] = p[1] * x + p[0];

    // Lorentzian: a*g^2/ ((x-c)^2 + g^2)
    REAL g; // HWHM
    REAL c; // position
    REAL a; // amplitude

    // derivatives
    float * current_derivative = derivative + point_index;

    current_derivative[0 * n_points] = 1; // wrt c
    current_derivative[1 * n_points] = x; // wrt m

    for (int i = 2; i < 26; i+=3) {
        // Lorentzian: a*g^2/ ((x-c)^2 + g^2)
        g = p[i] / 2;
        c = p[i+1];
        a = p[i+2];
        // value
        value[point_index] += a * g * g / ( (x - c) * (x - c) + g * g);

        // derivative
        // wrt fwhm
        current_derivative[i * n_points] = (a * g * (x - c) * (x - c)) / 
            ( (g * g + (x - c) * (x - c)) * (g * g + (x - c) * (x - c)) );
        // ((2 * a * g) / (g * g + (x - c) * (x - c))) - (
        //     (2 * a * g * g * g) / 
        //     ( (g * g + (x - c) * (x - c)) * (g * g + (x - c) * (x - c)) )
        // );
        // wrt position
        current_derivative[(i+1) * n_points] =  (2 * a * g * g * (x - c)) / 
            ( (g * g + (x - c) * (x - c)) * (g * g + (x - c) * (x - c)));
        // wrt amplitude
        current_derivative[(i+2) * n_points] = g * g / ((x - c) * (x - c) + g * g);
    }
}