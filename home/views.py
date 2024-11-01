from django.shortcuts import render, redirect, get_object_or_404, reverse
from django.http import HttpResponse, HttpResponseRedirect, FileResponse, StreamingHttpResponse, HttpRequest, JsonResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from .models import MidasModelFile, MidasConfigure
import shutil, os, psutil, subprocess, threading, math
from django.utils import timezone
import GPUtil
from django.db import transaction
import zipfile
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from time import sleep
from django.core.handlers.wsgi import WSGIRequest
from datetime import datetime

gRunCount = 0
gPending = 0
gStdout = {}

#================================================================================================
def index(request):
    midas_model_files = MidasModelFile.objects.all()
    paginator = Paginator(midas_model_files, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    running_models = MidasModelFile.objects.filter(status='RUNNING')
    ncnt = running_models.count()
    context = {
        'model_files': page_obj,
        'reload' : True if ncnt>0 else False,
    }
    return render(request, 'pages/model_list.html', context)

#================================================================================================
def upload_file(request):
    if request.method == 'POST':
        file = request.FILES.get('file')
        description = request.POST.get('description', '')

        if file:
            obj = MidasModelFile(file=file, description=description)

            _, ext = os.path.splitext(obj.file.name)
            if ext.lower() == '.mgb':
                obj.type = "GEN"                
            elif ext.lower() == '.mcb':
                obj.type = "CIVIL"                
            elif ext.lower() == '.gts':
                obj.type = "GTS"                
            elif ext.lower() == '.fea':
                obj.type = "FEA"
            elif ext.lower() == '.nfx':
                obj.type = "NFX"
            obj.status = 'NONE'
            
            with transaction.atomic():
                obj.save()
            
            messages.success(request, f'The {os.path.basename(obj.file.path)} has been uploaded successfully.')
        else:
            messages.warning(request, 'No file was submitted.')

        return redirect('upload_file')
    
    return render(request, 'pages/upload.html')

#================================================================================================
def configure_setting(request):
    if request.method == 'POST':
        max_run = request.POST.get('max_run')
        gen_path = request.POST.get('gen_path')
        civil_path = request.POST.get('civil_path')
        gts_path = request.POST.get('gts_path')
        fea_path = request.POST.get('fea_path')
        nfx_path = request.POST.get('nfx_path')

        config, created = MidasConfigure.objects.get_or_create(id=1)
        config.max_run = max_run
        config.gen_path = gen_path
        config.civil_path = civil_path
        config.gts_path = gts_path
        config.fea_path = fea_path
        config.nfx_path = nfx_path

        try:
            config.save()
            messages.success(request, 'Configuration saved successfully.')
            return redirect('configure')
        except ValidationError as e:
            messages.warning(request, 'Error saving configuration.')        
     
    config = MidasConfigure.objects.first()
    return render(request, 'pages/configure.html', {'config': config})

#================================================================================================
def model_list_view(request):
    midas_model_files = MidasModelFile.objects.all()
    paginator = Paginator(midas_model_files, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    running_models = MidasModelFile.objects.filter(status='RUNNING')
    ncnt = running_models.count()
    context = {
        'model_files': page_obj,
        'reload' : True if ncnt>0 else False,
    }
    return render(request, 'pages/model_list.html', context)

#================================================================================================
def download_model(request, pk):
    obj = get_object_or_404(MidasModelFile, pk=pk)
    file_name = os.path.basename(obj.file.path)
    fname, ext = os.path.splitext(file_name)
    zip_file = f'{fname}.zip'
    zip_path = default_storage.save(zip_file, ContentFile(''))
    with zipfile.ZipFile(default_storage.path(zip_path), 'w', zipfile.ZIP_DEFLATED) as zipf:
        file_path = obj.file.path.replace(file_name, '')
        files = os.listdir(file_path)                    
        for file in files:
            if os.path.isfile(os.path.join(file_path, file)):
                name, ext = os.path.splitext(file)
                
                if obj.type == 'CIVIL' or obj.type == 'GEN':
                    if name == fname and ext != '.76':
                        zipf.write(os.path.join(file_path, file), file)
                elif obj.type == 'GTS' or obj.type == 'FEA' or obj.type == 'NFX':
                    if fname in name and not ext.startswith('.bin'):
                        zipf.write(os.path.join(file_path, file), file)   
    
    # response = HttpResponse(default_storage.open(zip_path).read(), content_type='application/zip')    
    # response['Content-Disposition'] = f'attachment; filename={zip_file}'
 
    # default_storage.delete(zip_path)

    # FileResponse를 사용하여 파일을 스트리밍 방식으로 전송
    response = FileResponse(default_storage.open(zip_path, 'rb'), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename={zip_file}'

    # 응답이 완료된 후에 파일을 삭제하는 함수 정의
    def delete_file():
        try:
            default_storage.delete(zip_path)
        except Exception as e:
            print(f"Error deleting file: {e}")

    # 응답이 완료된 후에 파일을 삭제하도록 설정
    response.close = delete_file

    return response

#================================================================================================
def model_console_view(request, pk):
    global gStdout

    obj = get_object_or_404(MidasModelFile, pk=pk)
    context = {
        'obj': obj,
        'stdout': gStdout.get(obj.pk, ''),
        'reload': True,
    }

    return render(request, 'pages/model_console.html', context)

#================================================================================================
def model_detail_view(request, pk):
    global gStdout
    obj = get_object_or_404(MidasModelFile, pk=pk)
    if request.method == 'POST':        
        obj.description = request.POST.get('description')
        try:
            with transaction.atomic():
                obj.save()
            messages.success(request, f'The {os.path.basename(obj.file.path)} has been saved successfully.')
            return redirect('model_detail', pk=obj.pk)
        except ValidationError as e:
            messages.warning(request, f'An error occurred while saving the {os.path.basename(obj.file.path)}.')

    context = {
        'obj': obj,
        'stdout': gStdout.get(obj.pk, ''),
        'reload': True if obj.status == 'RUNNING' else False,
    }
    if obj.status == 'RUNNING':
        return render(request, 'pages/model_console.html', context)
    else:
        return render(request, 'pages/model_detail.html', context)

#================================================================================================
def delete_model(request, pk):
    global gRunCount
    obj = get_object_or_404(MidasModelFile, pk=pk)
    if request.method == 'POST':                
        try:
            if obj.status == 'RUNNING':
                terminate_process_and_children(request, obj.pid)                
                gRunCount -= 1
                if gRunCount < 0:
                    gRunCount = 0

            if os.path.exists(obj.file.path): 
                file_name = os.path.basename(obj.file.path)
                folder_path = obj.file.path.replace(file_name, '')
                shutil.rmtree(folder_path)
            obj.delete()
            messages.success(request, f'The {os.path.basename(obj.file.path)} has been deleted successfully.')
            return redirect('model_list')
        except ValidationError as e:
            messages.warning(request, f'An error occurred while deleting the {os.path.basename(obj.file.path)}.')

#================================================================================================
def run_model(request, pk):
    global gRunCount, gPending, gStdout    
    config = get_object_or_404(MidasConfigure, pk=1)
    obj = get_object_or_404(MidasModelFile, pk=pk)
    
    if obj.status == 'RUNNING' or obj.status == 'PENDING':
        messages.warning(request, f'{os.path.basename(obj.file.path)} is already running or pending.')
        return redirect('model_list')
    
    gStdout[obj.pk]= ''
    if gRunCount >= config.max_run:
        gPending += 1
        obj.status = 'PENDING'
        with transaction.atomic():
            obj.save()
        messages.success(request, f'{os.path.basename(obj.file.path)} is pending.')
    else:
        run_model_file(request, obj)
    
    return redirect('model_list')

#================================================================================================
def terminate_process_and_children(request, pid):
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            messages.success(request, f"Terminating child process {child.pid}")
            child.terminate()
        parent.terminate()
    except psutil.NoSuchProcess:
        messages.warning(request, f"No process with PID {pid} found.")
    except Exception as e:
        messages.warning(request, f"Error terminating processes: {e}")

#================================================================================================
def redirect_func():
    print('redirect_func')
    return redirect('model_list')

#================================================================================================
def subprocess_monitor(request, process, obj, redirect_func):
    global gRunCount, gPending, gStdout
    try:
        def read_stdout():            
            with process.stdout:
                for line in iter(process.stdout.readline, b''):
                    if isinstance(line, bytes):
                        line = line.decode('cp949', errors='replace').strip()
                    else:
                        line = line.strip()
                    
                    line = line.replace('\x08\x08\x08\x08', '')                        
                    if '%' in line:
                        stt = line.find('%')
                        end = line.rfind('%')
                        line = line[:stt-1]+line[end+1:]
                    elif '\r' in line:                         
                        line = line.split('\r')[-1]

                    current_time = datetime.now().strftime('[%H:%M:%S]')
                    if(len(line) > 0):
                        line = f'{current_time}   {line}'
                    gStdout[obj.pk] = gStdout[obj.pk] + line + '\n'

        stdout_thread = threading.Thread(target=read_stdout)
        stdout_thread.start()

        return_code = process.wait()

        stdout_thread.join()

        if return_code != 0:
            obj.status = 'STOPPED'                
        else:
            obj.status = 'COMPLETED'
        
        gRunCount -= 1
        if gRunCount < 0:
            gRunCount = 0

        obj.stdout = gStdout[obj.pk]
        gStdout[obj.pk] = ''
        with transaction.atomic():
            obj.save()
        
        if gPending > 0:
            run_pending_model(request)

    except subprocess.TimeoutExpired:
        messages.warning(request, f"Process {process.pid} timed out")
        obj.status = 'STOPPED'
        obj.stdout = gStdout[obj.pk]
        gStdout[obj.pk] = ''
        with transaction.atomic():
            obj.save()
    
    redirect_func()    

#================================================================================================
def run_model_file(request, obj):
    global gRunCount
    config = get_object_or_404(MidasConfigure, pk=1)
    str_exe = ''
    str_opt = ''
    if obj.type == 'GEN':
        str_exe = config.gen_path + r'\runSolver.exe'
        if not os.path.exists(str_exe):
            messages.warning(request, f"GEN path is not correct. Please configure GEN path in the Configuration.")
            return            
    elif obj.type == 'CIVIL':
        str_exe = config.civil_path + r'\runSolver.exe'
        if not os.path.exists(str_exe):
            messages.warning(request, f"Civil path is not correct. Please configure Civil path in the Configuration.")
            return            
    elif obj.type == 'GTS':
        str_exe = config.gts_path + r'\runSolver.exe'
        if not os.path.exists(str_exe):
            messages.warning(request, f"GTS path is not correct. Please configure GTS path in the Configuration.")
            return            
    elif obj.type == 'FEA':
        str_exe = config.fea_path + r'\runSolver.exe'
        if not os.path.exists(str_exe):
            messages.warning(request, f"FEA path is not correct. Please configure FEA path in the Configuration.")
            return            
    elif obj.type == 'NFX':
        str_exe = config.nfx_path + r'\nfxSolver.exe'
        if not os.path.exists(str_exe):
            messages.warning(request, f"NFX path is not correct. Please configure NFX path in the Configuration.")
            return            

    command = f'"{str_exe}" "{obj.file.path}" {str_opt}'
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    base, _ = os.path.splitext(obj.file.path)
    
    obj.status = 'RUNNING'
    obj.pid = process.pid
    obj.executed_at = timezone.now()
    obj.stdout = ''
    with transaction.atomic():
        obj.save()

    ## monitor process
    monitor_thread = threading.Thread(target=subprocess_monitor, args=(request, process, obj, redirect_func))
    monitor_thread.start()
    gRunCount += 1

#================================================================================================
def run_pending_model(request):
    global gPending    
    pending_models = MidasModelFile.objects.filter(status='PENDING')
    if pending_models.count() > 0:
        run_model_file(request, pending_models[0])
        gPending -= 1
    else:
        gPending = 0

#================================================================================================
def stop_model(request, pk):
    global gRunCount
    obj = get_object_or_404(MidasModelFile, pk=pk)
    if obj.status == 'RUNNING':
        try:
            terminate_process_and_children(request, obj.pid)
            obj.status = 'STOPPED'
            gRunCount -= 1
            if gRunCount < 0:
                gRunCount = 0
            with transaction.atomic():
                obj.save()            
            
        except psutil.NoSuchProcess:
            obj.status = 'STOPPED'
            gRunCount -= 1
            if gRunCount < 0:
                gRunCount = 0
            with transaction.atomic():
                obj.save()
            

        dir_path = os.path.dirname(obj.file.path)
        files = os.listdir(dir_path)
        remove_files = [file for file in files if '.bin' in file]
        for filename in remove_files:
            os.remove(os.path.join(dir_path, filename))

        if gPending > 0:
            run_pending_model(request)
    elif obj.status == 'PENDING':
        try:
            obj.status = 'STOPPED'
            with transaction.atomic():
                obj.save()
            
        except psutil.NoSuchProcess:
            obj.status = 'STOPPED'
            with transaction.atomic():
                obj.save()
            
    else:
        messages.warning(request, 'Model is not running.')
    return redirect('model_list')

#================================================================================================
def format_significant_digits(value, digits):
    try:
        value = float(value)
        if value == 0:
            return f"{0:.{digits}f}"
        else:
            return f"{value:.{digits}f}"
                
            scale = math.floor(math.log10(abs(value)))
            # Shift decimal point to make significant digits the integer part
            shifted = round(value / 10**scale, digits - 1)
            # Shift back to original scale
            return f"{shifted * 10**scale:.{digits}g}"
        
    except (ValueError, TypeError):
        return str(value)            

#================================================================================================
def get_systmem_info():
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    cpu_usage = psutil.cpu_percent(interval=1)
    total_cpus = psutil.cpu_count()
    cpu_usage_per_cpu = psutil.cpu_percent(interval=1, percpu=True)

    # Get GPU information
    gpus = GPUtil.getGPUs()
    gpu_info = [{
        'id': gpu.id,
        'name': gpu.name,
        'load': gpu.load * 100,
        'memory_total': format_significant_digits(gpu.memoryTotal, 3),
        'memory_used': format_significant_digits(gpu.memoryUsed, 3),
        'memory_free': format_significant_digits(gpu.memoryFree, 3),
        'temperature': gpu.temperature
    } for gpu in gpus]

    system_info = {
        'cpu_usage': cpu_usage,
        'total_cpus': total_cpus,
        'cpu_usage_per_cpu': cpu_usage_per_cpu,
        'memory_total': format_significant_digits(memory.total / (1024 ** 3), 3),  # Convert to GB
        'memory_available': format_significant_digits(memory.available / (1024 ** 3), 3),  # Convert to GB
        'memory_used': format_significant_digits(memory.used / (1024 ** 3), 3),  # Convert to GB
        'memory_free': format_significant_digits(memory.free / (1024 ** 3), 3),  # Convert to GB
        'disk_total': format_significant_digits(disk.total / (1024 ** 3), 3),  # Convert to GB
        'disk_used': format_significant_digits(disk.used / (1024 ** 3), 3),  # Convert to GB
        'disk_free': format_significant_digits(disk.free / (1024 ** 3), 3),  # Convert to GB
        'disk_percent': disk.percent,    
        'gpu_info': gpu_info,        
    }
    return system_info, gpu_info       

#================================================================================================ 
def system_info(request):
    system_info, gpu_info = get_systmem_info()
    running_models = MidasModelFile.objects.filter(status='RUNNING')
    pending_models = MidasModelFile.objects.filter(status='PENDING')
    context = dict(
        running_models = running_models,
        pending_models = pending_models,
        system_info = system_info,
        gpu_info = gpu_info,
    )

    return render(request, 'pages/system_info.html', context)

#================================================================================================
def model_view(request):
    return render(request, 'pages/model_view.html')
