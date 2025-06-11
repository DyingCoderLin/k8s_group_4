#!/bin/bash

#SBATCH --job-name=cuda_mm
#SBATCH --partition=dgx2
#SBATCH -N 1
#SBATCH --ntasks-per-node=4
#SBATCH --gres=gpu:1
#SBATCH --mail-type=end
#SBATCH --mail-user=nyte_plus@sjtu.edu.cn
#SBATCH --output=%j.out
#SBATCH --error=%j.err

cd CUDA_mm/build
cmake ..
make -j8
./cuda_matrix_multiply