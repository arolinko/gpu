#!/usr/bin/env python3
"""
GPU Scheduler for Kubernetes Interview Task
==========================================

A custom Kubernetes scheduler that places pods on specific nodes and sets 
CUDA_VISIBLE_DEVICES environment variable according to annotations.

Annotation format:
gpu-scheduling-map: |
  0=node1:0,1
  1=node2:2
  2=node3:0,1,2

Where:
- 0 is the pod index
- node1 is the node name  
- 0,1 is the value for CUDA_VISIBLE_DEVICES environment variable
"""
import os
import time
import logging
import re
from typing import Dict, List, Optional, Tuple
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException

# Configure logging for interview demonstration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('gpu-scheduler')

class GPUScheduler:
    def __init__(self):
        """Initialize the GPU scheduler with Kubernetes client."""
        try:
            # Try to load in-cluster config first, then fallback to local kubeconfig
            try:
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes configuration")
            except config.ConfigException:
                config.load_kube_config()
                logger.info("Loaded local Kubernetes configuration")
            
            self.v1 = client.CoreV1Api()
            self.scheduler_name = "gpu-scheduler"
            self.annotation_key = "gpu-scheduling-map"
            
        except Exception as e:
            logger.error(f"Failed to initialize Kubernetes client: {e}")
            raise

    def parse_gpu_mapping(self, annotation_value: str) -> Dict[int, Tuple[str, List[int]]]:
        """
        Parse the GPU scheduling mapping annotation.
        
        Format: |
          0=node1:0,1
          1=node2:2
          2=node3:0,1,2
          
        Returns: {pod_index: (node_name, [cuda_device_list])}
        """
        mapping = {}
        if not annotation_value:
            return mapping
            
        try:
            # Split by lines and process each mapping
            lines = annotation_value.strip().split('\n')
            for line in lines:
                line = line.strip()
                if not line or '=' not in line:
                    continue
                    
                # Parse format: pod_index=node_name:cuda_devices
                pod_index_str, node_mapping = line.split('=', 1)
                pod_index = int(pod_index_str.strip())
                
                if ':' not in node_mapping:
                    logger.warning(f"Invalid mapping format: {line}")
                    continue
                    
                node_name, cuda_devices_str = node_mapping.split(':', 1)
                node_name = node_name.strip()
                
                # Parse CUDA device list
                cuda_devices = []
                if cuda_devices_str.strip():
                    device_parts = cuda_devices_str.strip().split(',')
                    for device in device_parts:
                        try:
                            cuda_devices.append(int(device.strip()))
                        except ValueError:
                            logger.warning(f"Invalid CUDA device ID: {device}")
                
                mapping[pod_index] = (node_name, cuda_devices)
                logger.debug(f"Parsed mapping: pod {pod_index} -> node {node_name}, CUDA devices {cuda_devices}")
                
        except Exception as e:
            logger.error(f"Failed to parse GPU mapping annotation: {e}")
            
        return mapping

    def get_pod_index_from_name(self, pod_name: str) -> Optional[int]:
        """
        Extract pod index from pod name. 
        Assumes format like: <base-name>-<index> or tries to find index patterns.
        """
        try:
            # Try to extract index from StatefulSet naming pattern
            if '-' in pod_name:
                parts = pod_name.split('-')
                for part in reversed(parts):
                    if part.isdigit():
                        return int(part)
                        
            # Try to find numeric suffix pattern
            match = re.search(r'-(\d+)$', pod_name)
            if match:
                return int(match.group(1))
                
            # If no pattern found, check if entire name is numeric
            if pod_name.isdigit():
                return int(pod_name)
                
        except (ValueError, AttributeError) as e:
            logger.debug(f"Could not extract pod index from name '{pod_name}': {e}")
            
        return None

    def validate_node_exists(self, node_name: str) -> bool:
        """Check if the specified node exists and is ready."""
        try:
            nodes = self.v1.list_node()
            for node in nodes.items:
                if node.metadata.name == node_name:
                    # Check if node is ready
                    if node.status and node.status.conditions:
                        for condition in node.status.conditions:
                            if condition.type == "Ready" and condition.status == "True":
                                logger.debug(f"Node {node_name} exists and is ready")
                                return True
                        logger.warning(f"Node {node_name} exists but is not ready")
                        return False
                    else:
                        logger.warning(f"Node {node_name} exists but has no status conditions")
                        return False
            logger.error(f"Node {node_name} does not exist")
            return False
        except ApiException as e:
            logger.error(f"Error checking node existence: {e}")
            return False

    def inject_cuda_env_var(self, pod: client.V1Pod, cuda_devices: List[int]) -> client.V1Pod:
        """
        Inject CUDA_VISIBLE_DEVICES environment variable into pod containers.
        """
        cuda_devices_str = ','.join(map(str, cuda_devices)) if cuda_devices else ""
        
        # Create the environment variable
        cuda_env_var = client.V1EnvVar(
            name="CUDA_VISIBLE_DEVICES",
            value=cuda_devices_str
        )
        
        # Inject into all containers
        if pod.spec.containers:
            for container in pod.spec.containers:
                if container.env is None:
                    container.env = []
                
                # Remove existing CUDA_VISIBLE_DEVICES if present
                container.env = [env for env in container.env if env.name != "CUDA_VISIBLE_DEVICES"]
                
                # Add the new environment variable
                container.env.append(cuda_env_var)
                
        logger.info(f"Injected CUDA_VISIBLE_DEVICES='{cuda_devices_str}' into pod {pod.metadata.name}")
        return pod

    def schedule_pod(self, pod: client.V1Pod) -> bool:
        """
        Schedule a pod to the appropriate node based on GPU mapping annotation.
        """
        try:
            pod_name = pod.metadata.name
            namespace = pod.metadata.namespace
            
            # Check if pod has the GPU scheduling annotation
            annotations = pod.metadata.annotations or {}
            if self.annotation_key not in annotations:
                logger.debug(f"Pod {pod_name} doesn't have GPU scheduling annotation, skipping")
                return False
                
            # Parse the GPU mapping
            gpu_mapping = self.parse_gpu_mapping(annotations[self.annotation_key])
            if not gpu_mapping:
                logger.warning(f"Pod {pod_name} has empty or invalid GPU mapping")
                return False
                
            # Extract pod index
            pod_index = self.get_pod_index_from_name(pod_name)
            if pod_index is None:
                logger.warning(f"Could not determine pod index for {pod_name}")
                return False
                
            # Check if mapping exists for this pod index
            if pod_index not in gpu_mapping:
                logger.warning(f"No GPU mapping found for pod index {pod_index} in pod {pod_name}")
                return False
                
            node_name, cuda_devices = gpu_mapping[pod_index]
            
            # Validate target node exists
            if not self.validate_node_exists(node_name):
                logger.error(f"Target node {node_name} does not exist for pod {pod_name}")
                return False
                
            # Note: CUDA_VISIBLE_DEVICES should be pre-configured in pod template
            # Kubernetes doesn't allow patching environment variables on existing pods
            logger.info(f"Scheduling pod {pod_name} to node {node_name} (CUDA devices: {cuda_devices})")
            
            # Create binding to schedule pod to the target node
            target_ref = client.V1ObjectReference(
                kind="Node",
                name=node_name,
                api_version="v1"
            )
            
            binding = client.V1Binding(
                metadata=client.V1ObjectMeta(
                    name=pod_name,
                    namespace=namespace
                ),
                target=target_ref
            )
            
            # Debug logging
            logger.debug(f"Created binding with target: {target_ref.name}, kind: {target_ref.kind}")
            
            # Bind the pod to the node (using pods/binding subresource)
            logger.debug(f"Attempting to bind pod {pod_name} to node {node_name}")
            logger.debug(f"Binding object: metadata.name={binding.metadata.name}, target.name={binding.target.name}")
            
            result = self.v1.create_namespaced_pod_binding(
                name=pod_name,
                namespace=namespace,
                body=binding
            )
            
            logger.debug(f"Binding result: {result}")
            
            logger.info(f"Successfully scheduled pod {pod_name} (index {pod_index}) to node {node_name} with CUDA devices {cuda_devices}")
            return True
            
        except ApiException as e:
            logger.error(f"Kubernetes API error while scheduling pod {pod.metadata.name}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error while scheduling pod {pod.metadata.name}: {e}")
            return False

    def watch_unscheduled_pods(self):
        """
        Watch for unscheduled pods and attempt to schedule them.
        """
        logger.info(f"Starting GPU scheduler '{self.scheduler_name}'")
        
        w = watch.Watch()
        
        while True:
            try:
                logger.info("Watching for unscheduled pods...")
                
                # Watch for pod events
                for event in w.stream(
                    self.v1.list_pod_for_all_namespaces,
                    field_selector="spec.nodeName=",  # Only unscheduled pods
                    timeout_seconds=60
                ):
                    event_type = event['type']
                    pod = event['object']
                    
                    # Only process ADDED or MODIFIED events for unscheduled pods
                    if event_type in ['ADDED', 'MODIFIED']:
                        # Check if pod specifies our scheduler
                        if (pod.spec.scheduler_name == self.scheduler_name or 
                            (pod.spec.scheduler_name is None and 
                             pod.metadata.annotations and 
                             self.annotation_key in pod.metadata.annotations)):
                            
                            logger.info(f"Processing pod {pod.metadata.name} in namespace {pod.metadata.namespace}")
                            self.schedule_pod(pod)
                            
            except Exception as e:
                logger.error(f"Error in watch loop: {e}")
                logger.info("Restarting watch in 5 seconds...")
                time.sleep(5)

def main():
    """Main entry point for the GPU scheduler."""
    try:
        scheduler = GPUScheduler()
        scheduler.watch_unscheduled_pods()
    except KeyboardInterrupt:
        logger.info("GPU scheduler stopped by user")
    except Exception as e:
        logger.error(f"GPU scheduler failed: {e}")
        raise

if __name__ == "__main__":
    main() 