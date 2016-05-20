set terminal svg size 500,500 fname 'Verdana' fsize 10
set output 'multichain_scale.svg'
set   autoscale                        # scale axes automatically
unset log                              # remove any log-scaling
unset label                            # remove any previous labels
set xtic auto                          # set xtics automatically
set ytic auto                          # set ytics automatically
set title "Generation of multichain blocks on a personal computer"
set xlabel "Time (seconds)"
set ylabel "Number of blocks created"
plot "multichain_scale_experiment.dat" using 1:2 notitle with linespoints
unset output
