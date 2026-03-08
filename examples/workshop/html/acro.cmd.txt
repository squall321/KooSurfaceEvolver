// Evolver command file to make an ACROSPIN data file
// Usage: In Evolver, issue command: read "acro.cmd"
//   Set acroname to whatever you want the output file to be.
//   Then the command 'acro' will create the file.
//   You may reassign acroname in Evolver.  Otherwise
//   multiple uses will keep overwriting the same file.

acroname := "surface.acd"
aa := printf "EndPointList name X Y Z\n"
ab := foreach vertex do { printf "V%g %7.4g %7.4g %7.4g\n",id,x,y,z }
ac := printf "LineList from to Color Layer\n"
ad := foreach edge ee do { 
         foreach ee.vertex do { printf "V%g ",id };
         printf " 9 1\n" }
acro := {{ aa; ab; ac; ad } >>> acroname }


