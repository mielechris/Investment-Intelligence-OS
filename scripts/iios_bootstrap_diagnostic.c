/* One direct bootstrap child; owned unreaped PID only; no provider transport. */
#include <CommonCrypto/CommonDigest.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/sysctl.h>
#include <sys/wait.h>
#include <sys/xattr.h>
#include <sys/acl.h>
#include <libproc.h>
#include <poll.h>
#include <fcntl.h>
#include <signal.h>
#include <unistd.h>
#include <dirent.h>
#include <errno.h>
#include <time.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

typedef struct {const char *name,*sha;size_t size;} Attr;
typedef struct {const char *path,*sha,*target;off_t size;mode_t mode;uid_t uid;int type,first,count;} Pin;
#include "diagnostic_binding.h"
#ifndef ACCEPTANCE_MODE
#define ACCEPTANCE_MODE 0
#endif
static double deadline;
static int journal=-1;
static double now(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))_exit(91);return t.tv_sec+t.tv_nsec/1e9;}
static void note(const char *s){if(journal>=0){dprintf(journal,"%s\n",s);fsync(journal);}}
static void fail(const char *s){note(s);fprintf(stderr,"Diagnostic stopped: %s. No acceptance granted.\n",s);exit(1);}
#define NEED(x,s) do{if(!(x))fail(s);}while(0)
static void tick(void){NEED(now()<deadline,"TOTAL_DEADLINE");}
static void hex(const unsigned char *raw,char out[65]){for(int i=0;i<32;i++)sprintf(out+2*i,"%02x",raw[i]);out[64]=0;}
static int same(struct stat a,struct stat b){return a.st_dev==b.st_dev&&a.st_ino==b.st_ino&&a.st_size==b.st_size&&a.st_mode==b.st_mode&&a.st_uid==b.st_uid&&a.st_nlink==b.st_nlink&&a.st_mtimespec.tv_sec==b.st_mtimespec.tv_sec&&a.st_mtimespec.tv_nsec==b.st_mtimespec.tv_nsec&&a.st_ctimespec.tv_sec==b.st_ctimespec.tv_sec&&a.st_ctimespec.tv_nsec==b.st_ctimespec.tv_nsec;}
static void metadata(const Pin *p){
 char names[65536];ssize_t n=listxattr(p->path,names,sizeof names,XATTR_NOFOLLOW);NEED(n>=0,"XATTR_LIST");int found=0;
 for(ssize_t k=0;k<n;){size_t len=strnlen(names+k,(size_t)(n-k));NEED(k+len<n,"XATTR_NAME");int index=-1;
  for(int i=p->first;i<p->first+p->count;i++)if(!strcmp(names+k,ATTRS[i].name))index=i;
  NEED(index>=0,"XATTR_UNEXPECTED");const Attr *a=&ATTRS[index];NEED(a->size<=4*1024*1024,"XATTR_BOUND");
  void *data=malloc(a->size+1);NEED(data,"ALLOC");ssize_t size=getxattr(p->path,a->name,data,a->size+1,0,XATTR_NOFOLLOW);NEED(size==(ssize_t)a->size,"XATTR_SIZE");
  unsigned char digest[32];char h[65];CC_SHA256(data,(CC_LONG)size,digest);hex(digest,h);free(data);NEED(!strcmp(h,a->sha),"XATTR_HASH");found++;k+=(ssize_t)len+1;
 }
 NEED(found==p->count,"XATTR_MISSING");
 int fd=open(p->path,O_RDONLY|(p->type==3?O_SYMLINK:O_NOFOLLOW));NEED(fd>=0,"ACL_OPEN");
 errno=0;acl_t acl=acl_get_fd_np(fd,ACL_TYPE_EXTENDED);
 if(acl){NEED(acl_valid(acl)==0,"ACL_INVALID");acl_entry_t entry=NULL;errno=0;int rc=acl_get_entry(acl,ACL_FIRST_ENTRY,&entry);int error=errno;acl_free(acl);NEED(rc==-1&&error==EINVAL&&entry==NULL,"ACL_PRESENT");}
 else{NEED(errno==ENOENT,"ACL_READ");filesec_t security=filesec_init();NEED(security,"FILESEC_INIT");struct stat observed;int present=-1;NEED(!fstatx_np(fd,&observed,security),"FILESEC_STAT");NEED(!filesec_query_property(security,FILESEC_ACL,&present)&&present==0,"ACL_NOT_ABSENT");filesec_free(security);}
 close(fd);
}
static void verify_pin(const Pin *p){
 tick();struct stat st,after;NEED(!lstat(p->path,&st),"PIN_MISSING");NEED(st.st_uid==p->uid&&(st.st_mode&0777)==p->mode,"PIN_OWNER_MODE");
 if(p->type==2){NEED(S_ISDIR(st.st_mode),"DIRECTORY_TYPE");}
 else if(p->type==3){char target[4096];NEED(S_ISLNK(st.st_mode)&&st.st_nlink==1,"LINK_TYPE");ssize_t n=readlink(p->path,target,sizeof target);NEED(n==(ssize_t)strlen(p->target)&&!memcmp(target,p->target,(size_t)n),"LINK_TARGET");}
 else{
  NEED(S_ISREG(st.st_mode)&&st.st_size==p->size,"FILE_TYPE_SIZE");if(st.st_uid==getuid())NEED(st.st_nlink==1,"FILE_HARDLINK");
  int fd=open(p->path,O_RDONLY|O_NOFOLLOW);NEED(fd>=0,"FILE_OPEN");NEED(!fstat(fd,&after)&&same(st,after),"FILE_RACE");
  CC_SHA256_CTX ctx;CC_SHA256_Init(&ctx);unsigned char buf[1048576],digest[32];ssize_t n;off_t total=0;
  while((n=read(fd,buf,sizeof buf))>0){tick();total+=n;NEED(total<=p->size,"FILE_GROWTH");CC_SHA256_Update(&ctx,buf,(CC_LONG)n);}
  NEED(n==0&&total==p->size&&!fstat(fd,&after)&&same(st,after),"FILE_READ_RACE");close(fd);CC_SHA256_Final(digest,&ctx);char h[65];hex(digest,h);NEED(!strcmp(h,p->sha),"FILE_HASH");
 }
 if(p->first>=0)metadata(p);
 NEED(!lstat(p->path,&after)&&same(st,after),"PIN_RACE");
}
static const Pin *lookup(const char *path){for(size_t i=0;i<PIN_COUNT;i++)if(!strcmp(PINS[i].path,path))return &PINS[i];return NULL;}
static void tree(const char *path){DIR *d=opendir(path);NEED(d,"TREE_OPEN");struct dirent *e;while((e=readdir(d))){tick();if(!strcmp(e->d_name,".")||!strcmp(e->d_name,".."))continue;char full[4096];NEED(snprintf(full,sizeof full,"%s/%s",path,e->d_name)<(int)sizeof full,"TREE_PATH");const Pin *p=lookup(full);NEED(p,"TREE_ADDITION");if(p->type==2)tree(full);}closedir(d);}
static void identity(void){char buf[256];size_t n=sizeof buf;NEED(!sysctlbyname("kern.bootsessionuuid",buf,&n,NULL,0),"BOOT_QUERY");for(char *p=buf;*p;p++)if(*p>='A'&&*p<='Z')*p+=32;NEED(!strcmp(buf,BOOT_UUID),"BOOT_CHANGED");n=sizeof buf;NEED(!sysctlbyname("kern.osversion",buf,&n,NULL,0)&&!strcmp(buf,OS_BUILD),"OS_BUILD_CHANGED");}
static void private_ancestors(const char *path){
 char part[4096];NEED(strlen(path)<sizeof part&&path[0]=='/',"ANCESTOR_BOUND");strcpy(part,path);
 for(char *cursor=part+1;;cursor++){if(*cursor=='/'||*cursor==0){char saved=*cursor;*cursor=0;struct stat st;NEED(!lstat(part,&st)&&S_ISDIR(st.st_mode)&&!S_ISLNK(st.st_mode),"PRIVATE_PATH_ALIAS");NEED((st.st_uid==0||st.st_uid==getuid())&&!(st.st_mode&0022),"PRIVATE_ANCESTOR_OWNER");
  if(!strcmp(part,QUALIFICATION)||(!strncmp(part,QUALIFICATION,strlen(QUALIFICATION))&&part[strlen(QUALIFICATION)]=='/'))NEED(st.st_uid==getuid()&&((st.st_mode&0777)==0700||(st.st_mode&0777)==0500),"QUALIFICATION_MODE");
  *cursor=saved;if(!saved)break;}}
}
static pid_t ancestor_parent(pid_t pid){
 /* Full BSD info is denied for root-owned login; short BSD info supplies the exact required identity. */
 struct proc_bsdshortinfo info={0};NEED(proc_pidinfo(pid,PROC_PIDT_SHORTBSDINFO,0,&info,sizeof info)==sizeof info&&info.pbsi_pid==(uint32_t)pid,"ANCESTOR_IDENTITY");NEED(info.pbsi_ppid>1&&info.pbsi_ppid!=(uint32_t)pid,"ANCESTOR_CYCLE");return (pid_t)info.pbsi_ppid;
}
static void terminal(void){
 NEED(isatty(0)&&isatty(1)&&isatty(2),"TERMINAL_TTY");const char *v=getenv("TERM_PROGRAM");NEED(v&&!strcmp(v,"Apple_Terminal"),"TERMINAL_APPLICATION");
 const char *bad[]={"CODEX_THREAD_ID","CODEX_SANDBOX_NETWORK_DISABLED","VSCODE_PID","VSCODE_IPC_HOOK_CLI"};for(int i=0;i<4;i++)NEED(!getenv(bad[i]),"TERMINAL_CONTEXT");
 pid_t pid=getppid();int seen=0;
 for(int i=0;i<6&&pid>1;i++){char path[PROC_PIDPATHINFO_MAXSIZE];NEED(proc_pidpath(pid,path,sizeof path)>0,"ANCESTOR_PATH");if(!strcmp(path,TERMINAL_EXE)){seen=1;break;}
  NEED(!strcmp(path,"/bin/zsh")||!strcmp(path,"/bin/bash")||!strcmp(path,"/usr/bin/login"),"ANCESTOR_EXECUTABLE");
  pid=ancestor_parent(pid);
 }NEED(seen,"TERMINAL_ANCESTOR");
}
/* The direct child cannot have its PID reused while it remains unreaped. */
static int bounded(char *const argv[],const char *outpath,const char *errpath,double seconds,size_t maximum){
 tick();NEED(deadline-now()>seconds+8,"INSUFFICIENT_WINDOW");int pipes[2],errors[2];NEED(!pipe(pipes)&&!pipe(errors),"PIPE");
 int out=open(outpath,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600),err=open(errpath,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);NEED(out>=0&&err>=0,"OUTPUT_EXCLUSIVE");
 pid_t pid=fork();NEED(pid>=0,"FORK");
 if(pid==0){close(pipes[0]);close(errors[0]);dup2(pipes[1],1);dup2(errors[1],2);close(pipes[1]);close(errors[1]);close(out);close(err);if(journal>=0)close(journal);int nullfd=open("/dev/null",O_RDONLY);if(nullfd<0)_exit(125);dup2(nullfd,0);close(nullfd);
  signal(SIGALRM,SIG_DFL);alarm((unsigned int)seconds+2);int fdmax=getdtablesize();if(fdmax<3||fdmax>1048576)_exit(125);for(int fd=3;fd<fdmax;fd++)close(fd);
  char *const env[]={"PATH=/usr/bin:/bin","LANG=C","LC_ALL=C","TZ=UTC","OPENSSL_CONF=/dev/null","__CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0",NULL};execve(argv[0],argv,env);_exit(126);
 }
 close(pipes[1]);close(errors[1]);fcntl(pipes[0],F_SETFL,O_NONBLOCK);fcntl(errors[0],F_SETFL,O_NONBLOCK);double stop=now()+seconds;size_t bytes[2]={0,0};int fds[2]={pipes[0],errors[0]},dest[2]={out,err};int status=0,reaped=0,overflow=0,timed=0;
 while(!reaped){
  for(int i=0;i<2;i++){unsigned char buf[16384];ssize_t n;while((n=read(fds[i],buf,sizeof buf))>0){bytes[i]+=(size_t)n;if(bytes[i]>maximum){overflow=1;break;}ssize_t pos=0;while(pos<n){ssize_t w=write(dest[i],buf+pos,(size_t)(n-pos));if(w<=0){overflow=1;break;}pos+=w;}}}
  pid_t observed=waitpid(pid,&status,WNOHANG);if(observed==pid){reaped=1;break;}NEED(observed==0,"OWNED_CHILD_WAIT");
  if(overflow||now()>=stop){timed=!overflow;NEED(kill(pid,SIGKILL)==0||errno==ESRCH,"OWNED_CHILD_STOP");NEED(waitpid(pid,&status,0)==pid,"OWNED_CHILD_REAP");reaped=1;break;}
  struct pollfd ps[2]={{pipes[0],POLLIN,0},{errors[0],POLLIN,0}};poll(ps,2,25);
 }
 /* Drain bytes left after the exit; children cannot spawn descendants in workload mode. */
 for(int i=0;i<2;i++){unsigned char buf[16384];ssize_t n;while((n=read(fds[i],buf,sizeof buf))>0){bytes[i]+=(size_t)n;if(bytes[i]>maximum){overflow=1;break;}NEED(write(dest[i],buf,(size_t)n)==n,"OUTPUT_WRITE");}close(fds[i]);fsync(dest[i]);fchmod(dest[i],0400);close(dest[i]);}
 if(journal>=0){dprintf(journal,"OWNED_CHILD_WAIT_STATUS raw=%d exited=%d exit=%d signaled=%d signal=%d\n",status,WIFEXITED(status)?1:0,WIFEXITED(status)?WEXITSTATUS(status):-1,WIFSIGNALED(status)?1:0,WIFSIGNALED(status)?WTERMSIG(status):0);fsync(journal);}
 note(timed?"OWNED_CHILD_REAPED_TIMEOUT":overflow?"OWNED_CHILD_REAPED_OUTPUT_BOUND":"OWNED_CHILD_REAPED");
 return !timed&&!overflow&&WIFEXITED(status)&&WEXITSTATUS(status)==0;
}
static void signatures(void){
 for(size_t i=0;i<SIGN_COUNT;i++){char out[4096],err[4096];static int sequence=0;snprintf(out,sizeof out,"%s/signature-%03d.out",OUTPUT,sequence);snprintf(err,sizeof err,"%s/signature-%03d.err",OUTPUT,sequence++);
  char *argv[]={"/usr/bin/codesign","--verify","--strict","--all-architectures",NULL,NULL,NULL};
  if(SIGN_APPLE[i]){argv[4]="-R=anchor apple";argv[5]=(char*)SIGN_PATHS[i];}else argv[4]=(char*)SIGN_PATHS[i];
  NEED(bounded(argv,out,err,25,32768),"SIGNATURE_REJECTED");
 }
}
int main(int argc,char **argv){(void)argv;NEED(argc==1,"NO_ARGUMENTS");umask(077);deadline=now()+900;identity();terminal();private_ancestors(PACKAGE);private_ancestors(BOOTSTRAP);NEED(time(NULL)<EXPIRES_AT,"PACKAGE_EXPIRED");
 struct stat st;NEED(!lstat(PACKAGE,&st)&&S_ISDIR(st.st_mode)&&st.st_uid==getuid()&&(st.st_mode&0777)==0700,"PACKAGE_MODE");
 NEED(!chdir(PACKAGE),"WORKING_DIRECTORY");NEED(mkdir(OUTPUT,0700)==0,"ATTEMPT_ALREADY_EXISTS");journal=open(JOURNAL,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);NEED(journal>=0,"JOURNAL");note("BEGIN_ONE_ATTEMPT_DIAGNOSTIC_HISTORICAL_CLEANUP_NOT_ESTABLISHED");
 for(size_t i=0;i<PIN_COUNT;i++)verify_pin(&PINS[i]);tree(BOOTSTRAP);identity();signatures();note("PREFLIGHT_PINS_AND_SIGNATURES_VERIFIED");
 char *child[]={"/usr/bin/sandbox-exec","-f",PROFILE,INTERPRETER,"-I","-B","-S",CHILD_SCRIPT,NULL};
 note("WORKLOAD_BEGIN");int result=bounded(child,CHILD_OUTPUT,CHILD_ERROR,120,8*1024*1024);note(result?"WORKLOAD_REAPED_EXIT_ZERO":"WORKLOAD_REAPED_FAILED");identity();
 for(size_t i=0;i<PIN_COUNT;i++)verify_pin(&PINS[i]);tree(BOOTSTRAP);signatures();
 NEED(result,"DIAGNOSTIC_CHILD_FAILED");note(ACCEPTANCE_MODE?"REFERENCE_CHECKS_COMPLETE_PENDING_OFFLINE_ACCEPTANCE":"CAPTURE_COMPLETE_PENDING_OFFLINE_REVIEW_NO_ACCEPTANCE");fchmod(journal,0400);close(journal);puts(ACCEPTANCE_MODE?"Bootstrap reference checks captured. No acceptance granted. Return to Codex for independent review.":"Diagnostic captured. No acceptance granted. Return to Codex for independent review.");return 0;
}
