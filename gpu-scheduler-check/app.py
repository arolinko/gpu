#!/usr/bin/env python3
import os
import time
import logging
import socket
import json
import re
from datetime import datetime
from kubernetes import client, config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('gpu-scheduler-check')

def get_node_name():
    """Get the Kubernetes node name from environment variables."""
    # Try multiple environment variables that could contain the node name
    node_name = (
        os.environ.get('NODE_NAME') or 
        os.environ.get('KUBERNETES_NODE_NAME') or
        os.environ.get('MY_NODE_NAME') or
        socket.gethostname()
    )
    return node_name

def get_pod_index_from_name(pod_name: str) -> int:
    """Extract pod index from StatefulSet pod name (e.g., gpu-scheduler-check-0 -> 0)."""
    try:
        match = re.search(r'-(\d+)$', pod_name)
        if match:
            return int(match.group(1))
    except (ValueError, AttributeError):
        pass
    
    logger.warning(f"Could not extract pod index from name '{pod_name}', defaulting to 0")
    return 0

def parse_gpu_mapping(annotation_value: str) -> dict:
    """Parse the GPU scheduling mapping annotation."""
    mapping = {}
    if not annotation_value:
        return mapping
        
    try:
        lines = annotation_value.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line or '=' not in line:
                continue
                
            pod_index_str, node_mapping = line.split('=', 1)
            pod_index = int(pod_index_str.strip())
            
            if ':' not in node_mapping:
                continue
                
            node_name, cuda_devices_str = node_mapping.split(':', 1)
            cuda_devices = cuda_devices_str.strip()
            
            mapping[pod_index] = cuda_devices
            
    except Exception as e:
        logger.error(f"Failed to parse GPU mapping: {e}")
        
    return mapping

def setup_cuda_devices():
    """Set up CUDA_VISIBLE_DEVICES based on pod annotation and index."""
    try:
        # Initialize Kubernetes client
        try:
            config.load_incluster_config()
        except:
            logger.warning("Could not load in-cluster config, CUDA_VISIBLE_DEVICES may not be set correctly")
            return
            
        v1 = client.CoreV1Api()
        
        # Get pod information
        pod_name = os.environ.get('POD_NAME', 'unknown')
        pod_namespace = os.environ.get('POD_NAMESPACE', 'default')
        
        if pod_name == 'unknown':
            logger.warning("POD_NAME not available, cannot determine CUDA_VISIBLE_DEVICES")
            return
            
        # Get pod details
        pod = v1.read_namespaced_pod(name=pod_name, namespace=pod_namespace)
        
        # Extract GPU mapping from annotations
        annotations = pod.metadata.annotations or {}
        gpu_mapping_annotation = annotations.get('gpu-scheduling-map', '')
        
        if not gpu_mapping_annotation:
            logger.warning("No gpu-scheduling-map annotation found")
            return
            
        # Parse the mapping and get CUDA devices for this pod
        gpu_mapping = parse_gpu_mapping(gpu_mapping_annotation)
        pod_index = get_pod_index_from_name(pod_name)
        
        if pod_index in gpu_mapping:
            cuda_devices = gpu_mapping[pod_index]
            os.environ['CUDA_VISIBLE_DEVICES'] = cuda_devices
            logger.info(f"Set CUDA_VISIBLE_DEVICES={cuda_devices} for pod {pod_name} (index {pod_index})")
        else:
            logger.warning(f"No GPU mapping found for pod index {pod_index}")
            
    except Exception as e:
        logger.error(f"Error setting up CUDA devices: {e}")

def get_cuda_devices():
    """Get the CUDA_VISIBLE_DEVICES environment variable."""
    return os.environ.get('CUDA_VISIBLE_DEVICES', 'NOT_SET')

def get_pod_info():
    """Get pod information from environment variables."""
    return {
        'pod_name': os.environ.get('POD_NAME', 'unknown'),
        'pod_namespace': os.environ.get('POD_NAMESPACE', 'unknown'),
        'pod_ip': os.environ.get('POD_IP', 'unknown'),
        'service_account': os.environ.get('SERVICE_ACCOUNT', 'unknown')
    }

def log_status():
    """Log the current status including node name and CUDA devices."""
    node_name = get_node_name()
    cuda_devices = get_cuda_devices()
    pod_info = get_pod_info()
    
    status_info = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'node_name': node_name,
        'cuda_visible_devices': cuda_devices,
        'pod_info': pod_info,
        'hostname': socket.gethostname(),
        'all_env_vars': {k: v for k, v in os.environ.items() if k.startswith(('CUDA', 'NODE', 'POD', 'KUBERNETES'))}
    }
    
    # Log in both human-readable and JSON format
    logger.info(f"Node: {node_name} | CUDA_VISIBLE_DEVICES: {cuda_devices} | Pod: {pod_info['pod_name']}")
    logger.info(f"Status JSON: {json.dumps(status_info, indent=2)}")
    
    return status_info

def health_check():
    """Simple health check function."""
    try:
        node_name = get_node_name()
        cuda_devices = get_cuda_devices()
        
        if node_name and node_name != 'unknown':
            logger.debug("Health check passed - node name available")
            return True
        else:
            logger.warning("Health check warning - node name not available")
            return True  # Still consider healthy, just warn
            
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return False

def main():
    """Main application loop."""
    logger.info("Starting GPU Scheduler Check Service")
    logger.info("This service will log node name and CUDA_VISIBLE_DEVICES every 10 seconds")
    
    # Set up CUDA_VISIBLE_DEVICES from pod annotation
    setup_cuda_devices()
    
    # Initial log
    initial_status = log_status()
    logger.info(f"Initial configuration logged: {initial_status['node_name']}")
    
    # Setup health check endpoint (simple file-based for Kubernetes probes)
    try:
        with open('/tmp/healthy', 'w') as f:
            f.write('healthy\n')
        logger.info("Health check file created at /tmp/healthy")
    except Exception as e:
        logger.warning(f"Could not create health check file: {e}")
    
    iteration = 0
    
    try:
        while True:
            iteration += 1
            
            try:
                # Log current status
                current_status = log_status()
                
                # Perform health check every 10 iterations
                if iteration % 10 == 0:
                    if health_check():
                        logger.debug(f"Health check passed at iteration {iteration}")
                    else:
                        logger.error(f"Health check failed at iteration {iteration}")
                
                # Additional debug information every 60 iterations (10 minutes)
                if iteration % 60 == 0:
                    logger.info(f"Service has been running for {iteration * 10} seconds")
                    logger.info(f"Current working directory: {os.getcwd()}")
                    logger.info(f"Process ID: {os.getpid()}")
                    
                    # Log some system information
                    try:
                        import platform
                        logger.info(f"Platform: {platform.platform()}")
                        logger.info(f"Python version: {platform.python_version()}")
                    except ImportError:
                        logger.debug("Platform module not available")
                
            except Exception as e:
                logger.error(f"Error in status logging iteration {iteration}: {e}")
                
            # Wait for 10 seconds before next iteration
            time.sleep(10)
            
    except KeyboardInterrupt:
        logger.info("Service stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"Service failed with error: {e}")
        raise
    finally:
        logger.info("GPU Scheduler Check Service shutting down")

if __name__ == "__main__":
    main() 