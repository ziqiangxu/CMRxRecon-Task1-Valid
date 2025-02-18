#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri May 26 22:08:22 2023

@author: Jun Lyu
"""
import h5py
import os
import numpy as np
from loadFun import loadmat, kdata2img, multicoilkdata2img
from logger import Logger
import sys
import argparse
import pandas as pd
import scipy.io as scio
import time
from Evaluation import calmetric, save_metric, memo_metric0, save_df
# from CalEvalMap import CalSaveT2map, EvalMyo, CalSaveT1map
import gzip
import tarfile
import zipfile
import rarfile
import math
import json

sys.path = [
    os.path.abspath(__file__)[:-9]
] + sys.path

logger = Logger.to_file('custom_log.txt')

def get_max_value(psnr1, psnr2):
    if math.isnan(psnr1) and math.isnan(psnr2):
        return float('nan')
    elif math.isnan(psnr1):
        return psnr2
    elif math.isnan(psnr2):
        return psnr1
    else:
        return psnr1 if psnr1 > psnr2 else psnr2

def get_min_value(nmse1, nmse2):
    if math.isnan(nmse1) and math.isnan(nmse2):
        return float('nan')
    elif math.isnan(nmse1):
        return nmse2
    elif math.isnan(nmse2):
        return nmse1
    else:
        return nmse1 if nmse1 < nmse2 else nmse2

def get_mean_value(value1, value2):
    if np.isnan(value1) and np.isnan(value2):
        return np.nan
    elif np.isnan(value1):
        return value2
    elif np.isnan(value2):
        return value1
    else:
        return (value1 + value2) / 2

def get_mean_max_value(value1, value2):
    mean_value1 = np.nanmean(value1)
    mean_value2 = np.nanmean(value2)
    if np.isnan(mean_value1) and np.isnan(mean_value2):
        return np.nan
    elif np.isnan(mean_value1):
        return mean_value2
    elif np.isnan(mean_value2):
        return mean_value1
    else:
        return mean_value1 if mean_value1 > mean_value2 else mean_value2

'''processing gz file'''
def ungz(filename):
    gz_file = gzip.GzipFile(filename)
    filename = filename[:-3] # gz文件的单文件解压就是去掉 filename 后面的 .gz
    with open(filename, "wb+") as file:
        file.write(gz_file.read())
        return filename  # 这个gzip的函数需要返回值以进一步配合untar函数

'''processing tar ball'''
def untar(filename):
    tar = tarfile.open(filename)
    names = tar.getnames()
    folder_dir = '/'.join(filename.split('/')[:-1])
    # tar本身是将文件打包,解除打包会产生很多文件,因此需要建立文件夹存放
    # if not os.path.isdir(folder_dir):
    #     os.mkdir(folder_dir)
    for name in names:
        tar.extract(name, folder_dir)
    tar.close()
    return folder_dir

'''processing zip file'''
def unzip(filename):
    zip_file = zipfile.ZipFile(filename)
    folder_dir = '/'.join(filename.split('/')[:-1])
    # # 类似tar解除打包,建立文件夹存放解压的多个文件
    # if not os.path.isdir(folder_dir):
    #     os.mkdir(folder_dir)
    for names in zip_file.namelist():
        zip_file.extract(names, folder_dir)
    zip_file.close()
    return folder_dir

'''processing rar file'''
def unrar(filename):
    rar = rarfile.RarFile(filename)
    folder_dir = '/'.join(filename.split('/')[:-1])
    # if not os.path.isdir(folder_dir):
    #     os.mkdir(folder_dir)
    os.chdir(folder_dir)
    rar.extractall()
    rar.close()
    return folder_dir

'''unzip ziped file'''
def unzipfile(fpth):
    if '.' in fpth:
        suffix = fpth.split('.')[-1]
        if suffix == 'gz':
            new_filename = ungz(fpth)
            os.remove(fpth)
            if new_filename.split('.')[-1] == 'tar':
                folder_dir = untar(new_filename)
                os.remove(new_filename)
        elif suffix == 'tar':
            folder_dir = untar(fpth)
            os.remove(fpth)
        elif suffix == 'zip':
            folder_dir = unzip(fpth)
            os.remove(fpth)
        elif suffix == 'rar':
            folder_dir = unrar(fpth)
            os.remove(fpth)
        else:
            raise Exception('Not supported format')
        return folder_dir
    else:
        # Guess it is a zip file
        unzip(fpth)
        # raise Exception('Not supported format')

def compare_folder_names(path1, path2):
    # 获取路径1和路径2下的所有文件夹名字
    if os.path.exists(path2):
        folder_names1 = [name for name in os.listdir(path1) if os.path.isdir(os.path.join(path1, name))]
        folder_names2 = [name for name in os.listdir(path2) if os.path.isdir(os.path.join(path2, name))]
        folder_names1 = sorted(folder_names1)
        folder_names2 = sorted(folder_names2)
    else:
        flag = 0
        missing_folders = path2
        submit_folders = []
        return flag, missing_folders, submit_folders

    submit_folders = folder_names2
    # 比较文件夹名字是否一致
    if set(folder_names1) == set(folder_names2):
        flag = 4
        return flag, [], submit_folders
    else:
        missing_folders = list(set(folder_names1) - set(folder_names2))
        flag = 0
        return flag, missing_folders, submit_folders

def check_mat_files(path1, path2, folder_names, Sub_Task):
    flag = 4
    different_sizes = []
    missing_files = []
    openfail_files = []

    complete_folders = folder_names.copy()
    gt_num_file = 0
    task_num_file = 0
    for folder_name in folder_names:
        folder_path1 = os.path.join(path1, folder_name)
        folder_path2 = os.path.join(path2, folder_name)
        if Sub_Task == 'T2map' or Sub_Task == 'T1map':
            mat_file_path1 = os.path.join(folder_path1, Sub_Task+'.mat')
            mat_file_path2 = os.path.join(folder_path2, Sub_Task+'.mat')
        else:
            mat_file_path1 = os.path.join(folder_path1, 'cine_' + Sub_Task + '.mat')
            mat_file_path2 = os.path.join(folder_path2, 'cine_' + Sub_Task + '.mat')

        if os.path.exists(mat_file_path1):
            if not os.path.exists(mat_file_path2):
                missing_files.append(mat_file_path2)
                complete_folders.remove(folder_name)
                flag = 1
                continue

            # 打开MAT文件
            try:
                dataset1 = loadmat(mat_file_path1)
                gt_num_file = gt_num_file+1
                dataset2 = loadmat(mat_file_path2)
                task_num_file = task_num_file+1
            except OSError as e:
                openfail_files.append(mat_file_path2)
                complete_folders.remove(folder_name)
                flag = 2
                continue

            logger.log(f'Dataset shape, dataset1: {dataset1.shape}, dataset2: {dataset2.shape}')
            # 检查数据集的大小
            if len(dataset1) != len(dataset2):
                different_sizes.append((mat_file_path2))
                complete_folders.remove(folder_name)
                flag = 3
                continue
        else:
            complete_folders.remove(folder_name)

    return flag, different_sizes, missing_files, openfail_files, complete_folders, task_num_file, gt_num_file

def check_mapping_data(gt_dir, target_dir, R, Sub_Task):
    flag_folder, missing_folders, submit_folders = compare_folder_names(gt_dir, target_dir)
    flag_file, different_sizes, missing_files, openfail_files, complete_folders, task_num_file, gt_num_file = check_mat_files(gt_dir, target_dir,
                                                                                                  submit_folders,Sub_Task)

    return flag_folder, missing_folders, submit_folders, flag_file, different_sizes, missing_files, openfail_files, complete_folders, task_num_file, gt_num_file

def CalValue(complete_folders, gt_dir, target_dir, Sub_Task):
    target_dir = target_dir
    gt_dir = gt_dir

    PSNR_list = []
    SSIM_list = []
    NMSE_list = []
    # 遍历文件夹并计算Metric Value
    for folder in complete_folders:
        if Sub_Task == 'T2map' or Sub_Task == 'T1map':
            target_path = os.path.join(target_dir, folder, Sub_Task + '.mat')
            reference_path = os.path.join(gt_dir, folder, Sub_Task + '.mat')
        else:
            target_path = os.path.join(target_dir, folder, 'cine_' + Sub_Task + '.mat')
            reference_path = os.path.join(gt_dir, folder, 'cine_' + Sub_Task + '.mat')

        pred_recon = loadmat(target_path)
        gt_recon = loadmat(reference_path)
        [psnr_array, ssim_array, nmse_array] = calmetric(pred_recon, gt_recon)

        PSNR_list.append(np.mean(psnr_array))
        SSIM_list.append(np.mean(ssim_array))
        NMSE_list.append(np.mean(nmse_array))

    psnr_results = np.mean(PSNR_list)
    ssim_results = np.mean(SSIM_list)
    nmse_results = np.mean(NMSE_list)
    return psnr_results, ssim_results, nmse_results
'''
========================================= 需要上传 以下内容 ==============================================
'''
def get_args():
    """Set up command-line interface and get arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--submissionfile", type=str, required=True, 
                        help="""
                        Submission archive file or the directory contains test directory,
                        and this directory need include MultiCoil or SingleCoil
                        """)
    parser.add_argument("-g", "--goldstandard", type=str,required=True, help="Goldstandard for scoring")
    parser.add_argument("-t","--task", type=str, required=True, default="Cine", help = "Mapping or Cine")
    parser.add_argument("-r", "--results", type=str, required=True, default="results.json", help="Scoring results")
    return parser.parse_args()

def main():
    """Main function."""
    args = get_args()

    DataType = 'ValidationSet'
     
    # >>> Added by Daryl.Xu, prepare the submission file
    submission_file = args.submissionfile
    if os.path.isfile(submission_file):

        # submission_file是只读目录
        new_path =  'tmp-dir/submission.zip'
        assert 0 == os.system(f'mkdir tmp-dir && cp {submission_file} {new_path}'), 'Failed to make directory or copy file'
        unzipfile(new_path)
        # if submission_file.lower().endswith('.tar.gz'):
        #     target_dir = submission_file[:-7]
        # else:
        #     target_dir = submission_file[:-4]
        dir_name = os.path.dirname(new_path)
        submission_path = os.path.join(dir_name, 'Submission')
        multi_coil_path = os.path.join(dir_name, 'MultiCoil')
        single_coil_path = os.path.join(dir_name, 'SingleCoil')
        if os.path.isdir(submission_path):
            # submission_file = os.path.join(dir_name, 'Submission')
            data_base = os.path.join(dir_name, 'Submission')
        elif os.path.isdir(multi_coil_path) or os.path.isdir(single_coil_path):
            data_base = dir_name
        else:
            raise RuntimeError("No valid data found, please check the archive file's structure")
    elif os.path.isdir(submission_file):
        data_base = submission_file
    else:
        raise RuntimeError('submission_file is not a file or directory, make sure it exist')
    # os.system(f'echo ****; ls {data_base};echo *****')
    print(os.listdir(data_base))
    # <<<
    
    # data_base = os.path.join(submission_file, args.task)
    
    if args.task == 'Cine':
        Sub_Task = 'lax'
        Coil_Type = 'SingleCoil'
        # 待比较文件的目录
        target_dir04 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor04')
        target_dir08 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor08')
        target_dir10 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor10')
    
        # 参考文件的目录
        gt_dir04 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor04')
        gt_dir08 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor08')
        gt_dir10 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor10')
    
        flag_folder_lax_04_Single, missing_folders_lax_04_Single, submit_folders_lax_04_Single, flag_file_lax_04_Single, different_sizes_lax_04_Single, missing_files_lax_04_Single, openfail_files_lax_04_Single, complete_folders_lax_04_Single, num_task_lax_04_Single, num_gt_lax_04_Single = check_mapping_data(
            gt_dir04, target_dir04, '04', Sub_Task)
        flag_folder_lax_08_Single, missing_folders_lax_08_Single, submit_folders_lax_08_Single, flag_file_lax_08_Single, different_sizes_lax_08_Single, missing_files_lax_08_Single, openfail_files_lax_08_Single, complete_folders_lax_08_Single, num_task_lax_08_Single, num_gt_lax_08_Single = check_mapping_data(
            gt_dir08, target_dir08, '08', Sub_Task)
        flag_folder_lax_10_Single, missing_folders_lax_10_Single, submit_folders_lax_10_Single, flag_file_lax_10_Single, different_sizes_lax_10_Single, missing_files_lax_10_Single, openfail_files_lax_10_Single, complete_folders_lax_10_Single, num_task_lax_10_Single, num_gt_lax_10_Single = check_mapping_data(
            gt_dir10, target_dir10, '10', Sub_Task)

        variables = {
            "lax_04_Single": {
                "flag_folder": flag_folder_lax_04_Single,
                "missing_folders": missing_folders_lax_04_Single,
                "submit_folders": submit_folders_lax_04_Single,
                "flag_file": flag_file_lax_04_Single,
                "different_sizes": different_sizes_lax_04_Single,
                "missing_files": missing_files_lax_04_Single,
                "openfail_files": openfail_files_lax_04_Single,
                "complete_folders": complete_folders_lax_04_Single,
                "num_task_file": num_task_lax_04_Single,
                "num_gt_file": num_gt_lax_04_Single
            },
            "lax_08_Single": {
                "flag_folder": flag_folder_lax_08_Single,
                "missing_folders": missing_folders_lax_08_Single,
                "submit_folders": submit_folders_lax_08_Single,
                "flag_file": flag_file_lax_08_Single,
                "different_sizes": different_sizes_lax_08_Single,
                "missing_files": missing_files_lax_08_Single,
                "openfail_files": openfail_files_lax_08_Single,
                "complete_folders": complete_folders_lax_08_Single,
                "num_task_file": num_task_lax_08_Single,
                "num_gt_file": num_gt_lax_08_Single
            },
            "lax_10_Single": {
                "flag_folder": flag_folder_lax_10_Single,
                "missing_folders": missing_folders_lax_10_Single,
                "submit_folders": submit_folders_lax_10_Single,
                "flag_file": flag_file_lax_10_Single,
                "different_sizes": different_sizes_lax_10_Single,
                "missing_files": missing_files_lax_10_Single,
                "openfail_files": openfail_files_lax_10_Single,
                "complete_folders": complete_folders_lax_10_Single,
                "num_task_file": num_task_lax_10_Single,
                "num_gt_file": num_gt_lax_10_Single
            }
        }

        filename = "Lax_Single_Flags.json"

        with open(filename, mode='w') as file:
            json.dump(variables, file, indent=4)

        psnr_results_lax_04_Single, ssim_results_lax_04_Single, nmse_results_lax_04_Single = CalValue(
            complete_folders_lax_04_Single, gt_dir04, target_dir04, Sub_Task)
        psnr_results_lax_08_Single, ssim_results_lax_08_Single, nmse_results_lax_08_Single = CalValue(
            complete_folders_lax_08_Single, gt_dir08, target_dir08, Sub_Task)
        psnr_results_lax_10_Single, ssim_results_lax_10_Single, nmse_results_lax_10_Single = CalValue(
            complete_folders_lax_10_Single, gt_dir10, target_dir10, Sub_Task)
    
        Coil_Type = 'MultiCoil'
        # 待比较文件的目录
        target_dir04 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor04')
        target_dir08 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor08')
        target_dir10 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor10')
    
        # 参考文件的目录
        gt_dir04 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor04')
        gt_dir08 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor08')
        gt_dir10 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor10')
    
        flag_folder_lax_04_Multi, missing_folders_lax_04_Multi, submit_folders_lax_04_Multi, flag_file_lax_04_Multi, different_sizes_lax_04_Multi, missing_files_lax_04_Multi, openfail_files_lax_04_Multi, complete_folders_lax_04_Multi, num_task_lax_04_Multi, num_gt_lax_04_Multi = check_mapping_data(
            gt_dir04, target_dir04, '04', Sub_Task)
        flag_folder_lax_08_Multi, missing_folders_lax_08_Multi, submit_folders_lax_08_Multi, flag_file_lax_08_Multi, different_sizes_lax_08_Multi, missing_files_lax_08_Multi, openfail_files_lax_08_Multi, complete_folders_lax_08_Multi, num_task_lax_08_Multi, num_gt_lax_08_Multi = check_mapping_data(
            gt_dir08, target_dir08, '08', Sub_Task)
        flag_folder_lax_10_Multi, missing_folders_lax_10_Multi, submit_folders_lax_10_Multi, flag_file_lax_10_Multi, different_sizes_lax_10_Multi, missing_files_lax_10_Multi, openfail_files_lax_10_Multi, complete_folders_lax_10_Multi, num_task_lax_10_Multi, num_gt_lax_10_Multi = check_mapping_data(
            gt_dir10, target_dir10, '10', Sub_Task)

        variables = {
            "lax_04_Multi": {
                "flag_folder": flag_folder_lax_04_Multi,
                "missing_folders": missing_folders_lax_04_Multi,
                "submit_folders": submit_folders_lax_04_Multi,
                "flag_file": flag_file_lax_04_Multi,
                "different_sizes": different_sizes_lax_04_Multi,
                "missing_files": missing_files_lax_04_Multi,
                "openfail_files": openfail_files_lax_04_Multi,
                "complete_folders": complete_folders_lax_04_Multi,
                "num_task_file": num_task_lax_04_Multi,
                "num_gt_file": num_gt_lax_04_Multi
            },
            "lax_08_Multi": {
                "flag_folder": flag_folder_lax_08_Multi,
                "missing_folders": missing_folders_lax_08_Multi,
                "submit_folders": submit_folders_lax_08_Multi,
                "flag_file": flag_file_lax_08_Multi,
                "different_sizes": different_sizes_lax_08_Multi,
                "missing_files": missing_files_lax_08_Multi,
                "openfail_files": openfail_files_lax_08_Multi,
                "complete_folders": complete_folders_lax_08_Multi,
                "num_task_file": num_task_lax_08_Multi,
                "num_gt_file": num_gt_lax_08_Multi
            },
            "lax_10_Multi": {
                "flag_folder": flag_folder_lax_10_Multi,
                "missing_folders": missing_folders_lax_10_Multi,
                "submit_folders": submit_folders_lax_10_Multi,
                "flag_file": flag_file_lax_10_Multi,
                "different_sizes": different_sizes_lax_10_Multi,
                "missing_files": missing_files_lax_10_Multi,
                "openfail_files": openfail_files_lax_10_Multi,
                "complete_folders": complete_folders_lax_10_Multi,
                "num_task_file": num_task_lax_10_Multi,
                "num_gt_file": num_gt_lax_10_Multi
            }
        }

        filename = "Lax_Multi_Flags.json"

        with open(filename, mode='w') as file:
            json.dump(variables, file, indent=4)

    
        psnr_results_lax_04_Multi, ssim_results_lax_04_Multi, nmse_results_lax_04_Multi = CalValue(
            complete_folders_lax_04_Multi, gt_dir04, target_dir04, Sub_Task)
    
        psnr_results_lax_08_Multi, ssim_results_lax_08_Multi, nmse_results_lax_08_Multi = CalValue(
            complete_folders_lax_08_Multi, gt_dir08, target_dir08, Sub_Task)
    
        psnr_results_lax_10_Multi, ssim_results_lax_10_Multi, nmse_results_lax_10_Multi = CalValue(
            complete_folders_lax_10_Multi, gt_dir10, target_dir10, Sub_Task)

        psnr_lax_04 = get_mean_max_value(psnr_results_lax_04_Multi, psnr_results_lax_04_Single)
        psnr_lax_08 = get_mean_max_value(psnr_results_lax_08_Multi, psnr_results_lax_08_Single)
        psnr_lax_10 = get_mean_max_value(psnr_results_lax_10_Multi, psnr_results_lax_10_Single)
        ssim_lax_04 = get_mean_max_value(ssim_results_lax_04_Multi, ssim_results_lax_04_Single)
        ssim_lax_08 = get_mean_max_value(ssim_results_lax_08_Multi, ssim_results_lax_08_Single)
        ssim_lax_10 = get_mean_max_value(ssim_results_lax_10_Multi, ssim_results_lax_10_Single)
        nmse_lax_04 = get_mean_max_value(nmse_results_lax_04_Multi, nmse_results_lax_04_Single)
        nmse_lax_08 = get_mean_max_value(nmse_results_lax_08_Multi, nmse_results_lax_08_Single)
        nmse_lax_10 = get_mean_max_value(nmse_results_lax_10_Multi, nmse_results_lax_10_Single)
        
        Sub_Task = 'sax'
        Coil_Type = 'SingleCoil'
        # 待比较文件的目录
        target_dir04 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor04')
        target_dir08 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor08')
        target_dir10 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor10')
    
        # 参考文件的目录
        gt_dir04 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor04')
        gt_dir08 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor08')
        gt_dir10 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor10')
    
        flag_folder_sax_04_Single, missing_folders_sax_04_Single, submit_folders_sax_04_Single, flag_file_sax_04_Single, different_sizes_sax_04_Single, missing_files_sax_04_Single, openfail_files_sax_04_Single, complete_folders_sax_04_Single, num_task_sax_04_Single, num_gt_sax_04_Single = check_mapping_data(
            gt_dir04, target_dir04, '04', Sub_Task)
        flag_folder_sax_08_Single, missing_folders_sax_08_Single, submit_folders_sax_08_Single, flag_file_sax_08_Single, different_sizes_sax_08_Single, missing_files_sax_08_Single, openfail_files_sax_08_Single, complete_folders_sax_08_Single, num_task_sax_08_Single, num_gt_sax_08_Single = check_mapping_data(
            gt_dir08, target_dir08, '08', Sub_Task)
        flag_folder_sax_10_Single, missing_folders_sax_10_Single, submit_folders_sax_10_Single, flag_file_sax_10_Single, different_sizes_sax_10_Single, missing_files_sax_10_Single, openfail_files_sax_10_Single, complete_folders_sax_10_Single, num_task_sax_10_Single, num_gt_sax_10_Single = check_mapping_data(
            gt_dir10, target_dir10, '10', Sub_Task)

        variables = {
            "sax_04_Single": {
                "flag_folder": flag_folder_sax_04_Single,
                "missing_folders": missing_folders_sax_04_Single,
                "submit_folders": submit_folders_sax_04_Single,
                "flag_file": flag_file_sax_04_Single,
                "different_sizes": different_sizes_sax_04_Single,
                "missing_files": missing_files_sax_04_Single,
                "openfail_files": openfail_files_sax_04_Single,
                "complete_folders": complete_folders_sax_04_Single,
                "num_task_file": num_task_sax_04_Single,
                "num_gt_file": num_gt_sax_04_Single
            },
            "sax_08_Single": {
                "flag_folder": flag_folder_sax_08_Single,
                "missing_folders": missing_folders_sax_08_Single,
                "submit_folders": submit_folders_sax_08_Single,
                "flag_file": flag_file_sax_08_Single,
                "different_sizes": different_sizes_sax_08_Single,
                "missing_files": missing_files_sax_08_Single,
                "openfail_files": openfail_files_sax_08_Single,
                "complete_folders": complete_folders_sax_08_Single,
                "num_task_file": num_task_lax_08_Single,
                "num_gt_file": num_gt_lax_08_Single
            },
            "sax_10_Single": {
                "flag_folder": flag_folder_sax_10_Single,
                "missing_folders": missing_folders_sax_10_Single,
                "submit_folders": submit_folders_sax_10_Single,
                "flag_file": flag_file_sax_10_Single,
                "different_sizes": different_sizes_sax_10_Single,
                "missing_files": missing_files_sax_10_Single,
                "openfail_files": openfail_files_sax_10_Single,
                "complete_folders": complete_folders_sax_10_Single,
                "num_task_file": num_task_lax_10_Single,
                "num_gt_file": num_gt_lax_10_Single
            }
        }

        filename = "Sax_Single_Flags.json"

        with open(filename, mode='w') as file:
            json.dump(variables, file, indent=4)

        psnr_results_sax_04_Single, ssim_results_sax_04_Single, nmse_results_sax_04_Single = CalValue(
            complete_folders_sax_04_Single, gt_dir04, target_dir04, Sub_Task)
        psnr_results_sax_08_Single, ssim_results_sax_08_Single, nmse_results_sax_08_Single = CalValue(
            complete_folders_sax_08_Single, gt_dir08, target_dir08, Sub_Task)
        psnr_results_sax_10_Single, ssim_results_sax_10_Single, nmse_results_sax_10_Single = CalValue(
            complete_folders_sax_10_Single, gt_dir10, target_dir10, Sub_Task)
    
        Coil_Type = 'MultiCoil'
        # 待比较文件的目录
        target_dir04 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor04')
        target_dir08 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor08')
        target_dir10 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor10')
    
        # 参考文件的目录
        gt_dir04 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor04')
        gt_dir08 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor08')
        gt_dir10 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor10')
    
        flag_folder_sax_04_Multi, missing_folders_sax_04_Multi, submit_folders_sax_04_Multi, flag_file_sax_04_Multi, different_sizes_sax_04_Multi, missing_files_sax_04_Multi, openfail_files_sax_04_Multi, complete_folders_sax_04_Multi, num_task_sax_04_Multi, num_gt_sax_04_Multi = check_mapping_data(
            gt_dir04, target_dir04, '04', Sub_Task)
        flag_folder_sax_08_Multi, missing_folders_sax_08_Multi, submit_folders_sax_08_Multi, flag_file_sax_08_Multi, different_sizes_sax_08_Multi, missing_files_sax_08_Multi, openfail_files_sax_08_Multi, complete_folders_sax_08_Multi, num_task_sax_08_Multi, num_gt_sax_08_Multi = check_mapping_data(
            gt_dir08, target_dir08, '08', Sub_Task)
        flag_folder_sax_10_Multi, missing_folders_sax_10_Multi, submit_folders_sax_10_Multi, flag_file_sax_10_Multi, different_sizes_sax_10_Multi, missing_files_sax_10_Multi, openfail_files_sax_10_Multi, complete_folders_sax_10_Multi, num_task_sax_10_Multi, num_gt_sax_10_Multi = check_mapping_data(
            gt_dir10, target_dir10, '10', Sub_Task)

        variables = {
            "sax_04_Multi": {
                "flag_folder": flag_folder_sax_04_Multi,
                "missing_folders": missing_folders_sax_04_Multi,
                "submit_folders": submit_folders_sax_04_Multi,
                "flag_file": flag_file_sax_04_Multi,
                "different_sizes": different_sizes_sax_04_Multi,
                "missing_files": missing_files_sax_04_Multi,
                "openfail_files": openfail_files_sax_04_Multi,
                "complete_folders": complete_folders_sax_04_Multi,
                "num_task_file": num_task_sax_04_Multi,
                "num_gt_file": num_gt_sax_04_Multi
            },
            "sax_08_Multi": {
                "flag_folder": flag_folder_sax_08_Multi,
                "missing_folders": missing_folders_sax_08_Multi,
                "submit_folders": submit_folders_sax_08_Multi,
                "flag_file": flag_file_sax_08_Multi,
                "different_sizes": different_sizes_sax_08_Multi,
                "missing_files": missing_files_sax_08_Multi,
                "openfail_files": openfail_files_sax_08_Multi,
                "complete_folders": complete_folders_sax_08_Multi,
                "num_task_file": num_task_sax_08_Multi,
                "num_gt_file": num_gt_sax_08_Multi
            },
            "sax_10_Multi": {
                "flag_folder": flag_folder_sax_10_Multi,
                "missing_folders": missing_folders_sax_10_Multi,
                "submit_folders": submit_folders_sax_10_Multi,
                "flag_file": flag_file_sax_10_Multi,
                "different_sizes": different_sizes_sax_10_Multi,
                "missing_files": missing_files_sax_10_Multi,
                "openfail_files": openfail_files_sax_10_Multi,
                "complete_folders": complete_folders_sax_10_Multi,
                "num_task_file": num_task_sax_10_Multi,
                "num_gt_file": num_gt_sax_10_Multi
            }
        }

        filename = "Sax_Multi_Flags.json"

        with open(filename, mode='w') as file:
            json.dump(variables, file, indent=4)
    
        psnr_results_sax_04_Multi, ssim_results_sax_04_Multi, nmse_results_sax_04_Multi = CalValue(
            complete_folders_sax_04_Multi, gt_dir04, target_dir04, Sub_Task)
    
        psnr_results_sax_08_Multi, ssim_results_sax_08_Multi, nmse_results_sax_08_Multi = CalValue(
            complete_folders_sax_08_Multi, gt_dir08, target_dir08, Sub_Task)
    
        psnr_results_sax_10_Multi, ssim_results_sax_10_Multi, nmse_results_sax_10_Multi = CalValue(
            complete_folders_sax_10_Multi, gt_dir10, target_dir10, Sub_Task)

        psnr_sax_04 = get_mean_max_value(psnr_results_sax_04_Multi, psnr_results_sax_04_Single)
        psnr_sax_08 = get_mean_max_value(psnr_results_sax_08_Multi, psnr_results_sax_08_Single)
        psnr_sax_10 = get_mean_max_value(psnr_results_sax_10_Multi, psnr_results_sax_10_Single)
        ssim_sax_04 = get_mean_max_value(ssim_results_sax_04_Multi, ssim_results_sax_04_Single)
        ssim_sax_08 = get_mean_max_value(ssim_results_sax_08_Multi, ssim_results_sax_08_Single)
        ssim_sax_10 = get_mean_max_value(ssim_results_sax_10_Multi, ssim_results_sax_10_Single)
        nmse_sax_04 = get_mean_max_value(nmse_results_sax_04_Multi, nmse_results_sax_04_Single)
        nmse_sax_08 = get_mean_max_value(nmse_results_sax_08_Multi, nmse_results_sax_08_Single)
        nmse_sax_10 = get_mean_max_value(nmse_results_sax_10_Multi, nmse_results_sax_10_Single)
    
    else:
        Sub_Task = 'T1map'
        Coil_Type = 'SingleCoil'
        # 待比较文件的目录
        target_dir04 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor04')
        target_dir08 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor08')
        target_dir10 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor10')

        # 参考文件的目录
        gt_dir04 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor04')
        gt_dir08 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor08')
        gt_dir10 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor10')

        flag_folder_T1_04_Single, missing_folders_T1_04_Single, submit_folders_T1_04_Single, flag_file_T1_04_Single, different_sizes_T1_04_Single, missing_files_T1_04_Single, openfail_files_T1_04_Single, complete_folders_T1_04_Single, num_task_T1_04_Single, num_gt_T1_04_Single  = check_mapping_data(
            gt_dir04, target_dir04, '04', Sub_Task)
        flag_folder_T1_08_Single, missing_folders_T1_08_Single, submit_folders_T1_08_Single, flag_file_T1_08_Single, different_sizes_T1_08_Single, missing_files_T1_08_Single, openfail_files_T1_08_Single, complete_folders_T1_08_Single, num_task_T1_08_Single, num_gt_T1_08_Single  = check_mapping_data(
            gt_dir08, target_dir08, '08', Sub_Task)
        flag_folder_T1_10_Single, missing_folders_T1_10_Single, submit_folders_T1_10_Single, flag_file_T1_10_Single, different_sizes_T1_10_Single, missing_files_T1_10_Single, openfail_files_T1_10_Single, complete_folders_T1_10_Single, num_task_T1_10_Single, num_gt_T1_10_Single  = check_mapping_data(
            gt_dir10, target_dir10, '10', Sub_Task)

        data = {
            "T1_04_Single": {
                "flag_folder": flag_folder_T1_04_Single,
                "missing_folders": missing_folders_T1_04_Single,
                "submit_folders": submit_folders_T1_04_Single,
                "flag_file": flag_file_T1_04_Single,
                "different_sizes": different_sizes_T1_04_Single,
                "missing_files": missing_files_T1_04_Single,
                "openfail_files": openfail_files_T1_04_Single,
                "complete_folders": complete_folders_T1_04_Single,
                "num_task_file": num_task_T1_04_Single,
                "num_gt_file": num_gt_T1_04_Single
            },
            "T1_08_Single": {
                "flag_folder": flag_folder_T1_08_Single,
                "missing_folders": missing_folders_T1_08_Single,
                "submit_folders": submit_folders_T1_08_Single,
                "flag_file": flag_file_T1_08_Single,
                "different_sizes": different_sizes_T1_08_Single,
                "missing_files": missing_files_T1_08_Single,
                "openfail_files": openfail_files_T1_08_Single,
                "complete_folders": complete_folders_T1_08_Single,
                "num_task_file": num_task_T1_08_Single,
                "num_gt_file": num_gt_T1_08_Single
            },
            "T1_10_Single": {
                "flag_folder": flag_folder_T1_10_Single,
                "missing_folders": missing_folders_T1_10_Single,
                "submit_folders": submit_folders_T1_10_Single,
                "flag_file": flag_file_T1_10_Single,
                "different_sizes": different_sizes_T1_10_Single,
                "missing_files": missing_files_T1_10_Single,
                "openfail_files": openfail_files_T1_10_Single,
                "complete_folders": complete_folders_T1_10_Single,
                "num_task_file": num_task_T1_10_Single,
                "num_gt_file": num_gt_T1_10_Single
            }
        }

        filename = "T1_Single_Flags.json"

        with open(filename, mode='w') as file:
            json.dump(data, file, indent=4)

        psnr_results_T1_04_Single, ssim_results_T1_04_Single, nmse_results_T1_04_Single = CalValue(
            complete_folders_T1_04_Single, gt_dir04, target_dir04, Sub_Task)
        psnr_results_T1_08_Single, ssim_results_T1_08_Single, nmse_results_T1_08_Single = CalValue(
            complete_folders_T1_08_Single, gt_dir08, target_dir08, Sub_Task)
        psnr_results_T1_10_Single, ssim_results_T1_10_Single, nmse_results_T1_10_Single = CalValue(
            complete_folders_T1_10_Single, gt_dir10, target_dir10, Sub_Task)

        Coil_Type = 'MultiCoil'
        # 待比较文件的目录
        target_dir04 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor04')
        target_dir08 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor08')
        target_dir10 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor10')

        # 参考文件的目录
        gt_dir04 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor04')
        gt_dir08 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor08')
        gt_dir10 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor10')

        flag_folder_T1_04_Multi, missing_folders_T1_04_Multi, submit_folders_T1_04_Multi, flag_file_T1_04_Multi, different_sizes_T1_04_Multi, missing_files_T1_04_Multi, openfail_files_T1_04_Multi, complete_folders_T1_04_Multi, num_task_T1_04_Multi, num_gt_T1_04_Multi  = check_mapping_data(
            gt_dir04, target_dir04, '04', Sub_Task)
        flag_folder_T1_08_Multi, missing_folders_T1_08_Multi, submit_folders_T1_08_Multi, flag_file_T1_08_Multi, different_sizes_T1_08_Multi, missing_files_T1_08_Multi, openfail_files_T1_08_Multi, complete_folders_T1_08_Multi, num_task_T1_08_Multi, num_gt_T1_08_Multi  = check_mapping_data(
            gt_dir08, target_dir08, '08', Sub_Task)
        flag_folder_T1_10_Multi, missing_folders_T1_10_Multi, submit_folders_T1_10_Multi, flag_file_T1_10_Multi, different_sizes_T1_10_Multi, missing_files_T1_10_Multi, openfail_files_T1_10_Multi, complete_folders_T1_10_Multi, num_task_T1_10_Multi, num_gt_T1_10_Multi  = check_mapping_data(
            gt_dir10, target_dir10, '10', Sub_Task)

        variables = {
            "T1_04_Multi": {
                "flag_folder": flag_folder_T1_04_Multi,
                "missing_folders": missing_folders_T1_04_Multi,
                "submit_folders": submit_folders_T1_04_Multi,
                "flag_file": flag_file_T1_04_Multi,
                "different_sizes": different_sizes_T1_04_Multi,
                "missing_files": missing_files_T1_04_Multi,
                "openfail_files": openfail_files_T1_04_Multi,
                "complete_folders": complete_folders_T1_04_Multi,
                "num_task_file": num_task_T1_04_Multi,
                "num_gt_file": num_gt_T1_04_Multi
            },
            "T1_08_Multi": {
                "flag_folder": flag_folder_T1_08_Multi,
                "missing_folders": missing_folders_T1_08_Multi,
                "submit_folders": submit_folders_T1_08_Multi,
                "flag_file": flag_file_T1_08_Multi,
                "different_sizes": different_sizes_T1_08_Multi,
                "missing_files": missing_files_T1_08_Multi,
                "openfail_files": openfail_files_T1_08_Multi,
                "complete_folders": complete_folders_T1_08_Multi,
                "num_task_file": num_task_T1_08_Multi,
                "num_gt_file": num_gt_T1_08_Multi
            },
            "T1_10_Multi": {
                "flag_folder": flag_folder_T1_10_Multi,
                "missing_folders": missing_folders_T1_10_Multi,
                "submit_folders": submit_folders_T1_10_Multi,
                "flag_file": flag_file_T1_10_Multi,
                "different_sizes": different_sizes_T1_10_Multi,
                "missing_files": missing_files_T1_10_Multi,
                "openfail_files": openfail_files_T1_10_Multi,
                "complete_folders": complete_folders_T1_10_Multi,
                "num_task_file": num_task_T1_10_Multi,
                "num_gt_file": num_gt_T1_10_Multi
            }
        }

        filename = "T1_Multi_Flags.json"

        with open(filename, mode='w') as file:
            json.dump(variables, file, indent=4)


        psnr_results_T1_04_Multi, ssim_results_T1_04_Multi, nmse_results_T1_04_Multi = CalValue(
            complete_folders_T1_04_Multi, gt_dir04, target_dir04, Sub_Task)

        psnr_results_T1_08_Multi, ssim_results_T1_08_Multi, nmse_results_T1_08_Multi = CalValue(
            complete_folders_T1_08_Multi, gt_dir08, target_dir08, Sub_Task)

        psnr_results_T1_10_Multi, ssim_results_T1_10_Multi, nmse_results_T1_10_Multi = CalValue(
            complete_folders_T1_10_Multi, gt_dir10, target_dir10, Sub_Task)

        psnr_T1_04 = get_mean_max_value(psnr_results_T1_04_Multi, psnr_results_T1_04_Single)
        psnr_T1_08 = get_mean_max_value(psnr_results_T1_08_Multi, psnr_results_T1_08_Single)
        psnr_T1_10 = get_mean_max_value(psnr_results_T1_10_Multi, psnr_results_T1_10_Single)
        ssim_T1_04 = get_mean_max_value(ssim_results_T1_04_Multi, ssim_results_T1_04_Single)
        ssim_T1_08 = get_mean_max_value(ssim_results_T1_08_Multi, ssim_results_T1_08_Single)
        ssim_T1_10 = get_mean_max_value(ssim_results_T1_10_Multi, ssim_results_T1_10_Single)
        nmse_T1_04 = get_mean_max_value(nmse_results_T1_04_Multi, nmse_results_T1_04_Single)
        nmse_T1_08 = get_mean_max_value(nmse_results_T1_08_Multi, nmse_results_T1_08_Single)
        nmse_T1_10 = get_mean_max_value(nmse_results_T1_10_Multi, nmse_results_T1_10_Single)

        Sub_Task = 'T2map'
        Coil_Type = 'SingleCoil'
        # 待比较文件的目录
        target_dir04 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor04')
        target_dir08 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor08')
        target_dir10 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor10')

        # 参考文件的目录
        gt_dir04 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor04')
        gt_dir08 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor08')
        gt_dir10 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor10')

        flag_folder_T2_04_Single, missing_folders_T2_04_Single, submit_folders_T2_04_Single, flag_file_T2_04_Single, different_sizes_T2_04_Single, missing_files_T2_04_Single, openfail_files_T2_04_Single, complete_folders_T2_04_Single, num_task_T2_04_Single, num_gt_T2_04_Single = check_mapping_data(
            gt_dir04, target_dir04, '04', Sub_Task)
        flag_folder_T2_08_Single, missing_folders_T2_08_Single, submit_folders_T2_08_Single, flag_file_T2_08_Single, different_sizes_T2_08_Single, missing_files_T2_08_Single, openfail_files_T2_08_Single, complete_folders_T2_08_Single, num_task_T2_08_Single, num_gt_T2_08_Single = check_mapping_data(
            gt_dir08, target_dir08, '08', Sub_Task)
        flag_folder_T2_10_Single, missing_folders_T2_10_Single, submit_folders_T2_10_Single, flag_file_T2_10_Single, different_sizes_T2_10_Single, missing_files_T2_10_Single, openfail_files_T2_10_Single, complete_folders_T2_10_Single, num_task_T2_10_Single, num_gt_T2_10_Single = check_mapping_data(
            gt_dir10, target_dir10, '10', Sub_Task)
        variables = {
            "T2_04_Single": {
                "flag_folder": flag_folder_T2_04_Single,
                "missing_folders": missing_folders_T2_04_Single,
                "submit_folders": submit_folders_T2_04_Single,
                "flag_file": flag_file_T2_04_Single,
                "different_sizes": different_sizes_T2_04_Single,
                "missing_files": missing_files_T2_04_Single,
                "openfail_files": openfail_files_T2_04_Single,
                "complete_folders": complete_folders_T2_04_Single,
                "num_task_file": num_task_T2_04_Single,
                "num_gt_file": num_gt_T2_04_Single
            },
            "T2_08_Single": {
                "flag_folder": flag_folder_T2_08_Single,
                "missing_folders": missing_folders_T2_08_Single,
                "submit_folders": submit_folders_T2_08_Single,
                "flag_file": flag_file_T2_08_Single,
                "different_sizes": different_sizes_T2_08_Single,
                "missing_files": missing_files_T2_08_Single,
                "openfail_files": openfail_files_T2_08_Single,
                "complete_folders": complete_folders_T2_08_Single,
                "num_task_file": num_task_T2_08_Single,
                "num_gt_file": num_gt_T2_08_Single
            },
            "T2_10_Single": {
                "flag_folder": flag_folder_T2_10_Single,
                "missing_folders": missing_folders_T2_10_Single,
                "submit_folders": submit_folders_T2_10_Single,
                "flag_file": flag_file_T2_10_Single,
                "different_sizes": different_sizes_T2_10_Single,
                "missing_files": missing_files_T2_10_Single,
                "openfail_files": openfail_files_T2_10_Single,
                "complete_folders": complete_folders_T2_10_Single,
                "num_task_file": num_task_T2_10_Single,
                "num_gt_file": num_gt_T2_10_Single
            }
        }

        filename = "T2_Single_Flags.json"

        with open(filename, mode='w') as file:
            json.dump(variables, file, indent=4)


        psnr_results_T2_04_Single, ssim_results_T2_04_Single, nmse_results_T2_04_Single = CalValue(
            complete_folders_T2_04_Single, gt_dir04, target_dir04, Sub_Task)
        psnr_results_T2_08_Single, ssim_results_T2_08_Single, nmse_results_T2_08_Single = CalValue(
            complete_folders_T2_08_Single, gt_dir08, target_dir08, Sub_Task)
        psnr_results_T2_10_Single, ssim_results_T2_10_Single, nmse_results_T2_10_Single = CalValue(
            complete_folders_T2_10_Single, gt_dir10, target_dir10, Sub_Task)

        Coil_Type = 'MultiCoil'
        # 待比较文件的目录
        target_dir04 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor04')
        target_dir08 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor08')
        target_dir10 = os.path.join(data_base, Coil_Type, args.task, DataType, 'AccFactor10')

        # 参考文件的目录
        gt_dir04 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor04')
        gt_dir08 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor08')
        gt_dir10 = os.path.join(args.goldstandard, args.task, Coil_Type, args.task, DataType, 'AccFactor10')

        flag_folder_T2_04_Multi, missing_folders_T2_04_Multi, submit_folders_T2_04_Multi, flag_file_T2_04_Multi, different_sizes_T2_04_Multi, missing_files_T2_04_Multi, openfail_files_T2_04_Multi, complete_folders_T2_04_Multi, num_task_T2_04_Multi, num_gt_T2_04_Multi  = check_mapping_data(
            gt_dir04, target_dir04, '04', Sub_Task)
        flag_folder_T2_08_Multi, missing_folders_T2_08_Multi, submit_folders_T2_08_Multi, flag_file_T2_08_Multi, different_sizes_T2_08_Multi, missing_files_T2_08_Multi, openfail_files_T2_08_Multi, complete_folders_T2_08_Multi, num_task_T2_08_Multi, num_gt_T2_08_Multi  = check_mapping_data(
            gt_dir08, target_dir08, '08', Sub_Task)
        flag_folder_T2_10_Multi, missing_folders_T2_10_Multi, submit_folders_T2_10_Multi, flag_file_T2_10_Multi, different_sizes_T2_10_Multi, missing_files_T2_10_Multi, openfail_files_T2_10_Multi, complete_folders_T2_10_Multi, num_task_T2_10_Multi, num_gt_T2_10_Multi  = check_mapping_data(
            gt_dir10, target_dir10, '10', Sub_Task)

        variables = {
            "T2_04_Multi": {
                "flag_folder": flag_folder_T2_04_Multi,
                "missing_folders": missing_folders_T2_04_Multi,
                "submit_folders": submit_folders_T2_04_Multi,
                "flag_file": flag_file_T2_04_Multi,
                "different_sizes": different_sizes_T2_04_Multi,
                "missing_files": missing_files_T2_04_Multi,
                "openfail_files": openfail_files_T2_04_Multi,
                "complete_folders": complete_folders_T2_04_Multi,
                "num_task_file": num_task_T2_04_Multi,
                "num_gt_file": num_gt_T2_04_Multi
            },
            "T2_08_Multi": {
                "flag_folder": flag_folder_T2_08_Multi,
                "missing_folders": missing_folders_T2_08_Multi,
                "submit_folders": submit_folders_T2_08_Multi,
                "flag_file": flag_file_T2_08_Multi,
                "different_sizes": different_sizes_T2_08_Multi,
                "missing_files": missing_files_T2_08_Multi,
                "openfail_files": openfail_files_T2_08_Multi,
                "complete_folders": complete_folders_T2_08_Multi,
                "num_task_file": num_task_T2_08_Multi,
                "num_gt_file": num_gt_T2_08_Multi
            },
            "T2_10_Multi": {
                "flag_folder": flag_folder_T2_10_Multi,
                "missing_folders": missing_folders_T2_10_Multi,
                "submit_folders": submit_folders_T2_10_Multi,
                "flag_file": flag_file_T2_10_Multi,
                "different_sizes": different_sizes_T2_10_Multi,
                "missing_files": missing_files_T2_10_Multi,
                "openfail_files": openfail_files_T2_10_Multi,
                "complete_folders": complete_folders_T2_10_Multi,
                "num_task_file": num_task_T2_10_Multi,
                "num_gt_file": num_gt_T2_10_Multi
            }
        }

        filename = "T2_Multi_Flags.json"

        with open(filename, mode='w') as file:
            json.dump(variables, file, indent=4)

        psnr_results_T2_04_Multi, ssim_results_T2_04_Multi, nmse_results_T2_04_Multi = CalValue(
            complete_folders_T2_04_Multi, gt_dir04, target_dir04, Sub_Task)

        psnr_results_T2_08_Multi, ssim_results_T2_08_Multi, nmse_results_T2_08_Multi = CalValue(
            complete_folders_T2_08_Multi, gt_dir08, target_dir08, Sub_Task)

        psnr_results_T2_10_Multi, ssim_results_T2_10_Multi, nmse_results_T2_10_Multi = CalValue(
            complete_folders_T2_10_Multi, gt_dir10, target_dir10, Sub_Task)

        psnr_T2_04 = get_mean_max_value(psnr_results_T2_04_Multi, psnr_results_T2_04_Single)
        psnr_T2_08 = get_mean_max_value(psnr_results_T2_08_Multi, psnr_results_T2_08_Single)
        psnr_T2_10 = get_mean_max_value(psnr_results_T2_10_Multi, psnr_results_T2_10_Single)
        ssim_T2_04 = get_mean_max_value(ssim_results_T2_04_Multi, ssim_results_T2_04_Single)
        ssim_T2_08 = get_mean_max_value(ssim_results_T2_08_Multi, ssim_results_T2_08_Single)
        ssim_T2_10 = get_mean_max_value(ssim_results_T2_10_Multi, ssim_results_T2_10_Single)
        nmse_T2_04 = get_mean_max_value(nmse_results_T2_04_Multi, nmse_results_T2_04_Single)
        nmse_T2_08 = get_mean_max_value(nmse_results_T2_08_Multi, nmse_results_T2_08_Single)
        nmse_T2_10 = get_mean_max_value(nmse_results_T2_10_Multi, nmse_results_T2_10_Single)

    if args.task =='Cine':
        psnr_04 = get_mean_value(psnr_sax_04, psnr_lax_04)
        psnr_08 = get_mean_value(psnr_sax_08, psnr_lax_08)
        psnr_10 = get_mean_value(psnr_sax_10, psnr_lax_10)
        psnr_mean = np.mean([psnr_04, psnr_08, psnr_10])
        ssim_04 = get_mean_value(ssim_sax_04, ssim_lax_04)
        ssim_08 = get_mean_value(ssim_sax_08, ssim_lax_08)
        ssim_10 = get_mean_value(ssim_sax_10, ssim_lax_10)
        ssim_mean = np.mean([ssim_04, ssim_08, ssim_10])
        nmse_04 = get_mean_value(nmse_sax_04, nmse_lax_04)
        nmse_08 = get_mean_value(nmse_sax_08, nmse_lax_08)
        nmse_10 = get_mean_value(nmse_sax_10, nmse_lax_10)
        nmse_mean = np.mean([nmse_04, nmse_08, nmse_10])

        sum_numerator = num_task_lax_04_Single + num_task_lax_08_Single + num_task_lax_10_Single + \
                        num_task_sax_04_Single + num_task_sax_08_Single + num_task_sax_10_Single + \
                        num_task_lax_04_Multi + num_task_lax_08_Multi + num_task_lax_10_Multi + \
                        num_task_sax_04_Multi + num_task_sax_08_Multi + num_task_sax_10_Multi
        sum_denominator = num_gt_lax_04_Single + num_gt_lax_08_Single + num_gt_lax_10_Single + \
                          num_gt_sax_04_Single + num_gt_sax_08_Single + num_gt_sax_10_Single + \
                          num_gt_lax_04_Multi + num_gt_lax_08_Multi + num_gt_lax_10_Multi + \
                          num_gt_sax_04_Multi + num_gt_sax_08_Multi + num_gt_sax_10_Multi

        scores = {
            "Num_Files": f'{sum_numerator}/{666}',
            "num_file_Lax_04_Single": str(num_task_lax_04_Single)+ "/51", # + str(num_gt_lax_04_Single),
            "num_file_Lax_08_Single": str(num_task_lax_08_Single)+ "/51",# + str(num_gt_lax_08_Single),
            "num_file_Lax_10_Single": str(num_task_lax_10_Single)+ "/51",# + str(num_gt_lax_10_Single),
            "num_file_Sax_04_Single": str(num_task_sax_04_Single)+ "/60",# + str(num_gt_sax_04_Single),
            "num_file_Sax_08_Single": str(num_task_sax_08_Single)+ "/60",# + str(num_gt_sax_08_Single),
            "num_file_Sax_10_Single": str(num_task_sax_10_Single)+ "/60",# + str(num_gt_sax_10_Single),
            "num_file_Lax_04_Multi": str(num_task_lax_04_Multi)+ "/51",# + str(num_gt_lax_04_Multi),
            "num_file_Lax_08_Multi": str(num_task_lax_08_Multi)+ "/51",# + str(num_gt_lax_08_Multi),
            "num_file_Lax_10_Multi": str(num_task_lax_10_Multi)+ "/51",# + str(num_gt_lax_10_Multi),
            "num_file_Sax_04_Multi": str(num_task_sax_04_Multi)+ "/60",# + str(num_gt_sax_04_Multi),
            "num_file_Sax_08_Multi": str(num_task_sax_08_Multi)+ "/60",# + str(num_gt_sax_08_Multi),
            "num_file_Sax_10_Multi": str(num_task_sax_10_Multi)+ "/60",# + str(num_gt_sax_10_Multi),
            "Single_Lax_04_PSNR": np.round(np.mean(psnr_results_lax_04_Single), 4),
            "Single_Lax_08_PSNR": np.round(np.mean(psnr_results_lax_08_Single), 4),
            "Single_Lax_10_PSNR": np.round(np.mean(psnr_results_lax_10_Single), 4),
            "Single_Lax_04_SSIM": np.round(np.mean(ssim_results_lax_04_Single), 4),
            "Single_Lax_08_SSIM": np.round(np.mean(ssim_results_lax_08_Single), 4),
            "Single_Lax_10_SSIM": np.round(np.mean(ssim_results_lax_10_Single), 4),
            "Single_Lax_04_NMSE": np.round(np.mean(nmse_results_lax_04_Single), 4),
            "Single_Lax_08_NMSE": np.round(np.mean(nmse_results_lax_08_Single), 4),
            "Single_Lax_10_NMSE": np.round(np.mean(nmse_results_lax_10_Single), 4),
            "Multi_Lax_04_PSNR": np.round(np.mean(psnr_results_lax_04_Multi), 4),
            "Multi_Lax_08_PSNR": np.round(np.mean(psnr_results_lax_08_Multi), 4),
            "Multi_Lax_10_PSNR": np.round(np.mean(psnr_results_lax_10_Multi), 4),
            "Multi_Lax_04_SSIM": np.round(np.mean(ssim_results_lax_04_Multi), 4),
            "Multi_Lax_08_SSIM": np.round(np.mean(ssim_results_lax_08_Multi), 4),
            "Multi_Lax_10_SSIM": np.round(np.mean(ssim_results_lax_10_Multi), 4),
            "Multi_Lax_04_NMSE": np.round(np.mean(nmse_results_lax_04_Multi), 4),
            "Multi_Lax_08_NMSE": np.round(np.mean(nmse_results_lax_08_Multi), 4),
            "Multi_Lax_10_NMSE": np.round(np.mean(nmse_results_lax_10_Multi), 4),
            "Single_Sax_04_PSNR": np.round(np.mean(psnr_results_sax_04_Single), 4),
            "Single_Sax_08_PSNR": np.round(np.mean(psnr_results_sax_08_Single), 4),
            "Single_Sax_10_PSNR": np.round(np.mean(psnr_results_sax_10_Single), 4),
            "Single_Sax_04_SSIM": np.round(np.mean(ssim_results_sax_04_Single), 4),
            "Single_Sax_08_SSIM": np.round(np.mean(ssim_results_sax_08_Single), 4),
            "Single_Sax_10_SSIM": np.round(np.mean(ssim_results_sax_10_Single), 4),
            "Single_Sax_04_NMSE": np.round(np.mean(nmse_results_sax_04_Single), 4),
            "Single_Sax_08_NMSE": np.round(np.mean(nmse_results_sax_08_Single), 4),
            "Single_Sax_10_NMSE": np.round(np.mean(nmse_results_sax_10_Single), 4),
            "Multi_Sax_04_PSNR": np.round(np.mean(psnr_results_sax_04_Multi), 4),
            "Multi_Sax_08_PSNR": np.round(np.mean(psnr_results_sax_08_Multi), 4),
            "Multi_Sax_10_PSNR": np.round(np.mean(psnr_results_sax_10_Multi), 4),
            "Multi_Sax_04_SSIM": np.round(np.mean(ssim_results_sax_04_Multi), 4),
            "Multi_Sax_08_SSIM": np.round(np.mean(ssim_results_sax_08_Multi), 4),
            "Multi_Sax_10_SSIM": np.round(np.mean(ssim_results_sax_10_Multi), 4),
            "Multi_Sax_04_NMSE": np.round(np.mean(nmse_results_sax_04_Multi), 4),
            "Multi_Sax_08_NMSE": np.round(np.mean(nmse_results_sax_08_Multi), 4),
            "Multi_Sax_10_NMSE": np.round(np.mean(nmse_results_sax_10_Multi), 4),
            "Cine_PSNR": np.round(psnr_mean, 4),
            "Cine_SSIM": np.round(ssim_mean, 4),
            "Cine_NMSE": np.round(nmse_mean, 4)
        }
    else:
        psnr_04 = get_mean_value(psnr_T1_04, psnr_T2_04)
        psnr_08 = get_mean_value(psnr_T1_08, psnr_T2_08)
        psnr_10 = get_mean_value(psnr_T1_10, psnr_T2_10)
        psnr_mean = np.mean([psnr_04, psnr_08, psnr_10])
        ssim_04 = get_mean_value(ssim_T1_04, ssim_T2_04)
        ssim_08 = get_mean_value(ssim_T1_08, ssim_T2_08)
        ssim_10 = get_mean_value(ssim_T1_10, ssim_T2_10)
        ssim_mean = np.mean([ssim_04, ssim_08, ssim_10])
        nmse_04 = get_mean_value(nmse_T1_04, nmse_T2_04)
        nmse_08 = get_mean_value(nmse_T1_08, nmse_T2_08)
        nmse_10 = get_mean_value(nmse_T1_10, nmse_T2_10)
        nmse_mean = np.mean([nmse_04, nmse_08, nmse_10])

        sum_numerator = num_task_T1_04_Single + num_task_T1_08_Single + num_task_T1_10_Single + \
                        num_task_T2_04_Single + num_task_T2_08_Single + num_task_T2_10_Single + \
                        num_task_T1_04_Multi + num_task_T1_08_Multi + num_task_T1_10_Multi + \
                        num_task_T2_04_Multi + num_task_T2_08_Multi + num_task_T2_10_Multi
        sum_denominator = num_gt_T1_04_Single + num_gt_T1_08_Single + num_gt_T1_10_Single + \
                          num_gt_T2_04_Single + num_gt_T2_08_Single + num_gt_T2_10_Single + \
                          num_gt_T1_04_Multi + num_gt_T1_08_Multi + num_gt_T1_10_Multi + \
                          num_gt_T2_04_Multi + num_gt_T2_08_Multi + num_gt_T2_10_Multi


        scores = {
            "Num_Files": f'{sum_numerator}/{708}',
            "num_file_T1_04_Single": str(num_task_T1_04_Single)+ "/59", # + str(num_gt_T1_04_Single),
            "num_file_T1_08_Single": str(num_task_T1_08_Single)+ "/59", # + str(num_gt_T1_08_Single),
            "num_file_T1_10_Single": str(num_task_T1_10_Single)+ "/59", # + str(num_gt_T1_10_Single),
            "num_file_T2_04_Single": str(num_task_T2_04_Single)+ "/59", # + str(num_gt_T2_04_Single),
            "num_file_T2_08_Single": str(num_task_T2_08_Single)+ "/59", # + str(num_gt_T2_08_Single),
            "num_file_T2_10_Single": str(num_task_T2_10_Single)+ "/59", # + str(num_gt_T2_10_Single),
            "num_file_T1_04_Multi": str(num_task_T1_04_Multi)+ "/59", # + str(num_gt_T1_04_Multi),
            "num_file_T1_08_Multi": str(num_task_T1_08_Multi)+ "/59", # + str(num_gt_T1_04_Multi),
            "num_file_T1_10_Multi": str(num_task_T1_10_Multi)+ "/59", # + str(num_gt_T1_04_Multi),
            "num_file_T2_04_Multi": str(num_task_T2_04_Multi)+ "/59", # + str(num_gt_T2_04_Multi),
            "num_file_T2_08_Multi": str(num_task_T2_08_Multi)+ "/59", # + str(num_gt_T2_08_Multi),
            "num_file_T2_10_Multi": str(num_task_T2_10_Multi)+ "/59", # + str(num_gt_T2_10_Multi),
            "Single_T1_04_PSNR": np.round(np.mean(psnr_results_T1_04_Single), 4),
            "Single_T1_08_PSNR": np.round(np.mean(psnr_results_T1_08_Single), 4),
            "Single_T1_10_PSNR": np.round(np.mean(psnr_results_T1_10_Single), 4),
            "Single_T1_04_SSIM": np.round(np.mean(ssim_results_T1_04_Single), 4),
            "Single_T1_08_SSIM": np.round(np.mean(ssim_results_T1_08_Single), 4),
            "Single_T1_10_SSIM": np.round(np.mean(ssim_results_T1_10_Single), 4),
            "Single_T1_04_NMSE": np.round(np.mean(nmse_results_T1_04_Single), 4),
            "Single_T1_08_NMSE": np.round(np.mean(nmse_results_T1_08_Single), 4),
            "Single_T1_10_NMSE": np.round(np.mean(nmse_results_T1_10_Single), 4),
            "Multi_T1_04_PSNR": np.round(np.mean(psnr_results_T1_04_Multi), 4),
            "Multi_T1_08_PSNR": np.round(np.mean(psnr_results_T1_08_Multi), 4),
            "Multi_T1_10_PSNR": np.round(np.mean(psnr_results_T1_10_Multi), 4),
            "Multi_T1_04_SSIM": np.round(np.mean(ssim_results_T1_04_Multi), 4),
            "Multi_T1_08_SSIM": np.round(np.mean(ssim_results_T1_08_Multi), 4),
            "Multi_T1_10_SSIM": np.round(np.mean(ssim_results_T1_10_Multi), 4),
            "Multi_T1_04_NMSE": np.round(np.mean(nmse_results_T1_04_Multi), 4),
            "Multi_T1_08_NMSE": np.round(np.mean(nmse_results_T1_08_Multi), 4),
            "Multi_T1_10_NMSE": np.round(np.mean(nmse_results_T1_10_Multi), 4),
            "Single_T2_04_PSNR": np.round(np.mean(psnr_results_T2_04_Single), 4),
            "Single_T2_08_PSNR": np.round(np.mean(psnr_results_T2_08_Single), 4),
            "Single_T2_10_PSNR": np.round(np.mean(psnr_results_T2_10_Single), 4),
            "Single_T2_04_SSIM": np.round(np.mean(ssim_results_T2_04_Single), 4),
            "Single_T2_08_SSIM": np.round(np.mean(ssim_results_T2_08_Single), 4),
            "Single_T2_10_SSIM": np.round(np.mean(ssim_results_T2_10_Single), 4),
            "Single_T2_04_NMSE": np.round(np.mean(nmse_results_T2_04_Single), 4),
            "Single_T2_08_NMSE": np.round(np.mean(nmse_results_T2_08_Single), 4),
            "Single_T2_10_NMSE": np.round(np.mean(nmse_results_T2_10_Single), 4),
            "Multi_T2_04_PSNR": np.round(np.mean(psnr_results_T2_04_Multi), 4),
            "Multi_T2_08_PSNR": np.round(np.mean(psnr_results_T2_08_Multi), 4),
            "Multi_T2_10_PSNR": np.round(np.mean(psnr_results_T2_10_Multi), 4),
            "Multi_T2_04_SSIM": np.round(np.mean(ssim_results_T2_04_Multi), 4),
            "Multi_T2_08_SSIM": np.round(np.mean(ssim_results_T2_08_Multi), 4),
            "Multi_T2_10_SSIM": np.round(np.mean(ssim_results_T2_10_Multi), 4),
            "Multi_T2_04_NMSE": np.round(np.mean(nmse_results_T2_04_Multi), 4),
            "Multi_T2_08_NMSE": np.round(np.mean(nmse_results_T2_08_Multi), 4),
            "Multi_T2_10_NMSE": np.round(np.mean(nmse_results_T2_10_Multi), 4),
            "Mapping_PSNR": np.round(psnr_mean, 4),
            "Mapping_SSIM": np.round(ssim_mean, 4),
            "Mapping_NMSE": np.round(nmse_mean, 4)
        }
    with open(args.results, "w") as out:
        for k, v in scores.items():
            print(type(v), v)
            if type(v) != str and np.isnan(v):
                scores[k] = None
        results = {
            "submission_status": "SCORED",
            **scores
        }
        out.write(json.dumps(results, indent=4))
    logger.log('All message wrote!')
    logger.close()
    if os.path.exists('/app'):
        assert 0 == os.system('cp /app/README.txt . && zip better_log.zip *.json README.txt custom_log.txt')
    print('All checked!')

if __name__ == "__main__":
    start_time = time.time()
    main()
    end_time = time.time()
    # 计算代码执行时间
    execution_time = end_time - start_time
    print("代码执行时间：", execution_time, "秒")
